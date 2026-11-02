from odoo import _, api, fields, models


class MesLotTrace(models.TransientModel):
    _name = 'mes.lot.trace'
    _description = 'MES Lot Trace'
    _rec_name = 'lot_id'

    lot_id = fields.Many2one('stock.lot', string='Lot', required=True)
    product_id = fields.Many2one(related='lot_id.product_id')
    direction = fields.Selection([
        ('both', 'Both'),
        ('backward', 'Backward (made from)'),
        ('forward', 'Forward (went into)'),
    ], default='both', required=True)
    line_ids = fields.One2many('mes.lot.trace.line', 'trace_id', string='Trace', readonly=True)
    traced = fields.Boolean(readonly=True)
    backward_count = fields.Integer(compute='_compute_counts', string='Source Lots')
    forward_count = fields.Integer(compute='_compute_counts', string='Affected Lots')
    forward_on_hand = fields.Float(compute='_compute_counts', string='Affected Qty On Hand')

    @api.depends('line_ids')
    def _compute_counts(self):
        for trace in self:
            forward = trace.line_ids.filtered(lambda line: line.direction == 'forward')
            trace.forward_count = len(forward)
            trace.backward_count = len(trace.line_ids) - len(forward)
            trace.forward_on_hand = sum(forward.mapped('on_hand_qty'))

    def action_trace(self):
        self.ensure_one()
        directions = ['backward', 'forward'] if self.direction == 'both' else [self.direction]
        rows = [row for direction in directions for row in self.lot_id._mes_trace(direction)]
        self.line_ids = [(5, 0, 0)] + [(0, 0, row) for row in rows]
        self.traced = True
        return self._open_action()

    def _open_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lot Trace'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class MesLotTraceLine(models.TransientModel):
    _name = 'mes.lot.trace.line'
    _description = 'MES Lot Trace Line'
    _order = 'direction, depth, id'

    trace_id = fields.Many2one('mes.lot.trace', required=True, ondelete='cascade')
    direction = fields.Selection([('backward', 'Backward'), ('forward', 'Forward')], required=True)
    depth = fields.Integer(string='Level')
    lot_id = fields.Many2one('stock.lot', string='Lot', required=True)
    product_id = fields.Many2one(related='lot_id.product_id')
    parent_lot_id = fields.Many2one('stock.lot', string='Linked From')
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order')
    date = fields.Datetime()
    quantity = fields.Float(string='Qty')
    on_hand_qty = fields.Float(related='lot_id.product_qty', string='On Hand')
