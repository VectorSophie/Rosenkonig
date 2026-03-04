from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .rooms import room_manager
from ..engine.board import BoardState, state_from_dict
from ..engine.competitive import (
    AnalysisReport,
    EngineConfig,
    find_best_move,
    analyze_game,
)


router = APIRouter(tags=["analysis"])


class EngineConfigPayload(BaseModel):
    search_depth: int = Field(default=5, ge=1, le=8)
    num_determinizations: int = Field(default=20, ge=1, le=200)
    time_limit_seconds: float | None = Field(default=1.8, ge=0.05, le=30.0)
    max_nodes: int | None = Field(default=50000, ge=100, le=2_000_000)
    use_transposition_table: bool = True
    use_quiescence: bool = False
    random_seed: int = 7
    eval_weights: dict[str, float] = Field(default_factory=dict)
    risk_profile: str = Field(default="balanced")


class BestMoveRequest(BaseModel):
    room_id: str | None = None
    state: dict[str, Any] | None = None
    config: EngineConfigPayload | None = None


class AnalyzeGameRequest(BaseModel):
    room_id: str | None = None
    initial_state: dict[str, Any] | None = None
    move_history: list[dict[str, Any]] | None = None
    config: EngineConfigPayload | None = None


engine_config = EngineConfigPayload()


def _to_engine_config(payload: EngineConfigPayload | None) -> EngineConfig:
    source = engine_config if payload is None else payload
    return EngineConfig(
        search_depth=source.search_depth,
        num_determinizations=source.num_determinizations,
        time_limit_seconds=source.time_limit_seconds,
        max_nodes=source.max_nodes,
        use_transposition_table=source.use_transposition_table,
        use_quiescence=source.use_quiescence,
        random_seed=source.random_seed,
        eval_weights=source.eval_weights,
        risk_profile=source.risk_profile,
    )


def _report_to_dict(report: AnalysisReport) -> dict[str, Any]:
    return {
        "moves": [asdict(move) for move in report.moves],
        "initial_position": report.initial_position,
        "positions": report.positions,
        "score_timeline": report.score_timeline,
        "classifications": report.classifications,
        "alternatives": report.alternatives,
        "accuracy_by_player": report.accuracy_by_player,
        "largest_blunder": report.largest_blunder,
        "most_brilliant_move": report.most_brilliant_move,
    }


async def _resolve_state_and_history(
    room_id: str | None,
    initial_state: dict[str, Any] | None,
    move_history: list[dict[str, Any]] | None,
) -> tuple[BoardState, list[dict[str, Any]]]:
    if room_id is not None:
        try:
            room = await room_manager.get_room(room_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="room not found") from exc

        async with room.lock:
            state = room.engine.state.copy()
            state_history = state.history.copy()
            reconstructed = [entry.copy() for entry in state.move_history]
            if move_history is not None:
                reconstructed = move_history
            return state_from_dict(
                state_history[0]
            ) if state_history else state.copy(), reconstructed

    if initial_state is None:
        raise HTTPException(
            status_code=400, detail="initial_state or room_id is required"
        )

    state = state_from_dict(initial_state)
    history = move_history if move_history is not None else []
    return state, history


@router.get("/engine-config")
async def get_engine_config() -> dict[str, Any]:
    return engine_config.model_dump()


@router.post("/engine-config")
async def set_engine_config(config: EngineConfigPayload) -> dict[str, Any]:
    global engine_config
    engine_config = config
    return engine_config.model_dump()


@router.post("/best-move")
async def best_move(request: BestMoveRequest) -> dict[str, Any]:
    config = _to_engine_config(request.config)

    if request.room_id is not None:
        try:
            room = await room_manager.get_room(request.room_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="room not found") from exc
        async with room.lock:
            state = room.engine.state.copy()
    else:
        if request.state is None:
            raise HTTPException(status_code=400, detail="state or room_id is required")
        state = state_from_dict(request.state)

    result = find_best_move(state, config)
    return {
        "best_move": result.best_move,
        "expected_score": result.expected_score,
        "principal_variation": result.principal_variation,
        "move_evaluations": result.move_evaluations,
        "move_classifications": result.move_classifications,
        "move_explanations": {
            key: asdict(explanation)
            for key, explanation in result.move_explanations.items()
        },
        "evaluation_breakdowns": {
            key: asdict(breakdown)
            for key, breakdown in result.evaluation_breakdowns.items()
        },
        "root_evaluation": asdict(result.root_evaluation),
        "diagnostics": result.diagnostics,
    }


@router.post("/analyze-game")
async def analyze_game_endpoint(request: AnalyzeGameRequest) -> dict[str, Any]:
    config = _to_engine_config(request.config)
    initial_state, move_history = await _resolve_state_and_history(
        request.room_id,
        request.initial_state,
        request.move_history,
    )

    if not move_history:
        raise HTTPException(
            status_code=400,
            detail="move_history is required when room_id cannot provide explicit move list",
        )

    report = analyze_game(initial_state, move_history, config)
    return _report_to_dict(report)
