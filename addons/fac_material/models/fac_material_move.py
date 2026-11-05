from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

from .fac_material import QTY_DIGITS

STATES = [
    ('draft', 'Draft'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]

MOVE_TYPES = [
    ('in', 'Receipt'),
    ('out', 'Issue'),
]


class FacMaterialMove(models.Model):
    _name = 'fac.material.move'
    _description = 'Material Move'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    material_id = fields.Many2one('fac.material', string='Material', required=True,
                                  ondelete='restrict', index=True)
    uom = fields.Char(related='material_id.uom')
    move_type = fields.Selection(MOVE_TYPES, string='Type', required=True, default='in')
    quantity = fields.Float(string='Quantity', required=True, digits=QTY_DIGITS, default=1.0)
    date = fields.Datetime(string='Date', required=True, default=fields.Datetime.now)
    # Free-text source/destination, e.g. a supplier name or a work order reference.
    reference = fields.Char(string='Source / Destination', help="e.g. supplier or WO/00001")
    user_id = fields.Many2one('res.users', string='Handled By', default=lambda self: self.env.user)
    state = fields.Selection(STATES, string='Status', required=True, default='draft',
                             readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') != 'New':
                continue
            number = self.env['ir.sequence'].next_by_code('fac.material.move')
            if number:
                vals['name'] = number
        return super().create(vals_list)

    @api.constrains('quantity')
    def _check_quantity(self):
        for move in self:
            if move.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))

    # EB: execution steps without business meaning of their own.

    def _check_state(self, allowed_states, action_label):
        """Raise if any record is not in one of allowed_states."""
        for move in self:
            if move.state not in allowed_states:
                raise UserError(_(
                    "Move %(name)s cannot be %(action)s while it is %(state)s.",
                    name=move.name, action=action_label, state=dict(STATES)[move.state],
                ))

    def _check_available(self):
        """Raise if an issue would take more than is on hand."""
        self.ensure_one()
        if self.move_type != 'out':
            return
        on_hand = self.material_id.qty_on_hand
        if float_compare(self.quantity, on_hand, precision_digits=QTY_DIGITS[1]) > 0:
            raise UserError(_(
                "Not enough %(material)s: %(qty)s %(uom)s requested, %(on_hand)s on hand.",
                material=self.material_id.name, qty=self.quantity, uom=self.uom, on_hand=on_hand,
            ))

    def _set_state(self, new_state):
        """Write the new status."""
        self.write({'state': new_state})

    # BM: one business rule each.

    def confirm(self):
        """A draft move is done; an issue may not take more than is on hand. One move at a time."""
        self._check_state({'draft'}, _("confirmed"))
        for move in self:
            move._check_available()
            move._set_state('done')

    def cancel(self):
        """Only a draft move is cancelled. A done move is corrected with a reverse move."""
        self._check_state({'draft'}, _("cancelled"))
        self._set_state('cancelled')

    # FA steps: the form buttons call these.

    def action_confirm(self):
        """Move flow step: Draft -> Done."""
        self.confirm()

    def action_cancel(self):
        """Move flow step: Draft -> Cancelled."""
        self.cancel()
