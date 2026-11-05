from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

QTY_DIGITS = (16, 3)


class FacMaterial(models.Model):
    _name = 'fac.material'
    _description = 'Material'
    _order = 'code'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, copy=False)
    category = fields.Char(string='Category')
    uom = fields.Char(string='Unit', required=True, default='EA')
    location = fields.Char(string='Storage Location')
    min_qty = fields.Float(string='Minimum Stock', digits=QTY_DIGITS)
    qty_on_hand = fields.Float(string='On Hand', digits=QTY_DIGITS,
                               compute='_compute_qty_on_hand', store=True)
    is_below_min = fields.Boolean(string='Below Minimum', compute='_compute_is_below_min', store=True)
    move_ids = fields.One2many('fac.material.move', 'material_id', string='Moves')
    move_count = fields.Integer(string='Move Count', compute='_compute_move_count')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Notes')

    _code_unique = models.Constraint('unique(code)', 'Material code must be unique.')

    @api.constrains('min_qty')
    def _check_min_qty(self):
        for material in self:
            if material.min_qty < 0:
                raise ValidationError(_("Minimum stock cannot be negative."))

    # EB: execution steps without business meaning of their own.

    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.move_type')
    def _compute_qty_on_hand(self):
        """On hand = sum of done receipts minus sum of done issues."""
        for material in self:
            done_moves = material.move_ids.filtered(lambda m: m.state == 'done')
            receipts = done_moves.filtered(lambda m: m.move_type == 'in')
            issues = done_moves.filtered(lambda m: m.move_type == 'out')
            received = sum(receipts.mapped('quantity'))
            issued = sum(issues.mapped('quantity'))
            material.qty_on_hand = received - issued

    @api.depends('qty_on_hand', 'min_qty')
    def _compute_is_below_min(self):
        for material in self:
            material.is_below_min = float_compare(
                material.qty_on_hand, material.min_qty, precision_digits=QTY_DIGITS[1]) < 0

    @api.depends('move_ids')
    def _compute_move_count(self):
        for material in self:
            material.move_count = len(material.move_ids)

    # AC parts: screen navigation.

    def _open_new_move(self, move_type):
        """Open a draft move form for this material, pre-filled with move_type."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Receipt') if move_type == 'in' else _('Issue'),
            'res_model': 'fac.material.move',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_material_id': self.id, 'default_move_type': move_type},
        }

    def action_new_receipt(self):
        """Open a new receipt (stock in) for this material."""
        return self._open_new_move('in')

    def action_new_issue(self):
        """Open a new issue (stock out) for this material."""
        return self._open_new_move('out')

    def action_view_moves(self):
        """Open the moves of this material."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Moves'),
            'res_model': 'fac.material.move',
            'view_mode': 'list,form',
            'domain': [('material_id', '=', self.id)],
            'context': {'default_material_id': self.id},
        }
