from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    def _mes_trace(self, direction):
        """Walk completed manufacturing links from these lots, level by level.

        ``direction`` is ``backward`` (what the lot was made from) or ``forward``
        (what it went into). Each lot appears once, at its shortest distance.
        A component without lot tracking ends the chain, as no lot was recorded for it.
        """
        link = 'consume_line_ids' if direction == 'backward' else 'produce_line_ids'
        rows = []
        visited = set(self.ids)
        frontier = self
        depth = 0
        while frontier:
            depth += 1
            found = {}
            lines = self.env['stock.move.line'].search([
                ('lot_id', 'in', frontier.ids),
                ('state', '=', 'done'),
                (link, '!=', False),
            ])
            for line in lines:
                for linked in line[link].filtered(lambda ml: ml.lot_id and ml.state == 'done'):
                    if linked.lot_id.id in visited:
                        continue
                    finished = line if direction == 'backward' else linked
                    row = found.setdefault(linked.lot_id.id, {
                        'direction': direction,
                        'depth': depth,
                        'lot_id': linked.lot_id.id,
                        'parent_lot_id': line.lot_id.id,
                        'production_id': finished.move_id.production_id.id,
                        'date': finished.date,
                        'quantity': 0,
                    })
                    row['quantity'] += linked.quantity
            visited.update(found)
            rows.extend(found.values())
            frontier = self.browse(found)
        return rows

    def action_open_mes_trace(self):
        self.ensure_one()
        trace = self.env['mes.lot.trace'].create({'lot_id': self.id})
        trace.action_trace()
        return trace._open_action()
