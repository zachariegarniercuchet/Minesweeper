"""
Minesweeper ("Demineur") core engine — Python port of engine.js.

This is a line-for-line equivalent of the JS engine used by the web page,
so that a solver playing through Python sees *exactly* the same rules and
the exact same boards (same levels.json) as a human playing the HTML page.

Cell states: 'hidden' | 'revealed' | 'flagged'
Game status: 'ready' | 'playing' | 'won' | 'lost'
"""
from dataclasses import dataclass, field


def in_bounds(width, height, x, y):
    return 0 <= x < width and 0 <= y < height


def neighbors_of(width, height, x, y):
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if in_bounds(width, height, nx, ny):
                out.append((nx, ny))
    return out


@dataclass
class Game:
    width: int
    height: int
    mines: int
    is_mine: list
    adjacent: list
    cell_state: list
    status: str = "ready"
    revealed_count: int = 0
    flag_count: int = 0


def create_game(width, height, mine_cells):
    """mine_cells: iterable of (x, y) pairs."""
    mine_cells = list(mine_cells)
    is_mine = [[False] * width for _ in range(height)]
    for x, y in mine_cells:
        if not in_bounds(width, height, x, y):
            raise ValueError(f"Mine out of bounds: ({x}, {y})")
        is_mine[y][x] = True

    adjacent = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if is_mine[y][x]:
                continue
            count = 0
            for nx, ny in neighbors_of(width, height, x, y):
                if is_mine[ny][nx]:
                    count += 1
            adjacent[y][x] = count

    cell_state = [["hidden"] * width for _ in range(height)]

    return Game(
        width=width, height=height, mines=len(mine_cells),
        is_mine=is_mine, adjacent=adjacent, cell_state=cell_state,
    )


def _reveal_single(game, x, y):
    if game.cell_state[y][x] != "hidden":
        return
    game.cell_state[y][x] = "revealed"
    game.revealed_count += 1


def _reveal_all_mines_on_loss(game):
    for y in range(game.height):
        for x in range(game.width):
            if game.is_mine[y][x] and game.cell_state[y][x] == "hidden":
                game.cell_state[y][x] = "revealed"


def reveal(game, x, y):
    """Reveal (x, y). Flood-fills through connected 0-cells, exactly like engine.js."""
    if game.status in ("won", "lost"):
        return game
    if not in_bounds(game.width, game.height, x, y):
        return game
    if game.cell_state[y][x] != "hidden":
        return game

    if game.status == "ready":
        game.status = "playing"

    if game.is_mine[y][x]:
        _reveal_single(game, x, y)
        game.status = "lost"
        _reveal_all_mines_on_loss(game)
        return game

    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        if game.cell_state[cy][cx] != "hidden":
            continue
        _reveal_single(game, cx, cy)
        if game.adjacent[cy][cx] == 0:
            for nx, ny in neighbors_of(game.width, game.height, cx, cy):
                if game.cell_state[ny][nx] == "hidden" and not game.is_mine[ny][nx]:
                    stack.append((nx, ny))

    _check_win(game)
    return game


def toggle_flag(game, x, y):
    if game.status in ("won", "lost"):
        return game
    if not in_bounds(game.width, game.height, x, y):
        return game
    s = game.cell_state[y][x]
    if s == "hidden":
        game.cell_state[y][x] = "flagged"
        game.flag_count += 1
    elif s == "flagged":
        game.cell_state[y][x] = "hidden"
        game.flag_count -= 1
    return game


def chord(game, x, y):
    """Reveal all unflagged neighbors of a satisfied numbered cell at once."""
    if game.status in ("won", "lost"):
        return game
    if not in_bounds(game.width, game.height, x, y):
        return game
    if game.cell_state[y][x] != "revealed":
        return game

    number = game.adjacent[y][x]
    if number == 0:
        return game

    neigh = neighbors_of(game.width, game.height, x, y)
    flagged = [(nx, ny) for nx, ny in neigh if game.cell_state[ny][nx] == "flagged"]
    if len(flagged) != number:
        return game

    for nx, ny in neigh:
        if game.cell_state[ny][nx] == "hidden":
            reveal(game, nx, ny)
            if game.status == "lost":
                break
    return game


def _check_win(game):
    total_safe = game.width * game.height - game.mines
    if game.revealed_count >= total_safe and game.status != "lost":
        game.status = "won"
        for y in range(game.height):
            for x in range(game.width):
                if game.is_mine[y][x] and game.cell_state[y][x] == "hidden":
                    game.cell_state[y][x] = "flagged"


def hidden_cells(game):
    """All currently hidden, unflagged cell coordinates."""
    out = []
    for y in range(game.height):
        for x in range(game.width):
            if game.cell_state[y][x] == "hidden":
                out.append((x, y))
    return out
