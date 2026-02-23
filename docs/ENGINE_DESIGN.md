# Engine Design

The game engine handles the core mechanics of Rosenkönig, including board state, move generation, and scoring.

## Board Representation

The board is an 11x11 grid. Each cell can be empty, occupied by a Red crown, or occupied by a White crown.

```text
    0 1 2 3 4 5 6 7 8 9 10
 0  . . . . . . . . . . .
 1  . . . . . . . . . . .
 2  . . . . . . . . . . .
 3  . . . . . . . . . . .
 4  . . . . . . . . . . .
 5  . . . . . K . . . . .  <-- Crown (K) starts at (5,5)
 6  . . . . . . . . . . .
 7  . . . . . . . . . . .
 8  . . . . . . . . . . .
 9  . . . . . . . . . . .
10  . . . . . . . . . . .
```

Internally, the board is represented as a 2D array or a flat list of 121 integers.

## Move Generation

Moves are determined by the Crown's current position and the cards in a player's hand. Each card specifies a direction and a distance (1, 2, or 3).

### Directions
There are 8 possible directions:
- N, NE, E, SE, S, SW, W, NW

### Validation Logic
A move is valid if:
1.  The target coordinates are within the 11x11 bounds.
2.  The target cell is empty (unless a Knight card is used to flip an opponent's piece).
3.  The player has the corresponding card in their hand.

## Scoring (Connectivity)

Scoring is based on the size of contiguous groups of crowns of the same color.

### Calculation
1.  Identify all connected groups of crowns (using BFS or DFS).
2.  For each group, count the number of crowns (n).
3.  The score for that group is n squared (n²).
4.  The total score is the sum of all group scores.

Example: A group of 4 crowns is worth 16 points. Two separate groups of 2 crowns are worth 4 + 4 = 8 points.

## Complexity Analysis

- **Move Generation**: O(H) where H is the number of cards in hand (max 5). Very efficient.
- **Scoring**: O(B) where B is the number of cells on the board (121). We visit each cell once during the group finding process.
- **Memory**: O(B) to store the board state.
