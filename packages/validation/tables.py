from typing import List, Tuple
from packages.core.domain.node import TableNode


class TableValidator:
    @staticmethod
    def validate_table(table: TableNode) -> Tuple[bool, List[str]]:
        errors = []
        if table.num_rows <= 0 or table.num_cols <= 0:
            errors.append(f"Table {table.node_id} has invalid dimensions: {table.num_rows}x{table.num_cols}")
        
        expected_cells = table.num_rows * table.num_cols
        if len(table.cells) > 0 and len(table.cells) != expected_cells:
            # Table might have spans, so verify cell coordinates
            pass
        return len(errors) == 0, errors
