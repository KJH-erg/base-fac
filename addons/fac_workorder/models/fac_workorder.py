from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

STATES = [
    ('planned', 'Planned'),
    ('in_progress', 'In Progress'),
    ('on_hold', 'On Hold'),
    ('done', 'Done'),
]


class FacWorkorder(models.Model):
    _name = 'fac.workorder'
    _description = 'Work Order'
    _order = 'planned_start desc, id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    product_name = fields.Char(string='Product', required=True)
    quantity = fields.Float(string='Quantity', required=True, default=1.0)
    # Equipment is referenced by name/code text only; no link to another FAC's model.
    equipment_ref = fields.Char(string='Equipment', help="Equipment name or code")
    assignee_id = fields.Many2one('res.users', string='Assignee')
    planned_start = fields.Datetime(string='Planned Start')
    date_started = fields.Datetime(string='Started On', readonly=True, copy=False)
    date_done = fields.Datetime(string='Finished On', readonly=True, copy=False)
    hold_reason = fields.Char(string='Hold Reason', copy=False)
    state = fields.Selection(STATES, string='Status', required=True, default='planned',
                             readonly=True, copy=False)
    note = fields.Text(string='Instructions')

    @api.constrains('quantity')
    def _check_quantity(self):
        for workorder in self:
            if workorder.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') != 'New':
                continue
            number = self.env['ir.sequence'].next_by_code('fac.workorder')
            if number:
                vals['name'] = number
        return super().create(vals_list)

    # EB: execution steps without business meaning of their own.

    def _check_state(self, allowed_states, action_label):
        """Raise if any record is not in one of allowed_states."""
        for workorder in self:
            if workorder.state not in allowed_states:
                raise UserError(_(
                    "Work order %(name)s cannot be %(action)s while it is %(state)s.",
                    name=workorder.name, action=action_label,
                    state=dict(STATES)[workorder.state],
                ))

    def _set_state(self, new_state):
        """Write the new status."""
        self.write({'state': new_state})

    def _stamp(self, field_name):
        """Write the current time into field_name."""
        self.write({field_name: fields.Datetime.now()})

    def _clear(self, field_name):
        """Empty field_name."""
        self.write({field_name: False})

    # BM: one business rule each.

    def start(self):
        """A planned work order goes in progress; the start time is recorded."""
        self._check_state({'planned'}, _("started"))
        self._set_state('in_progress')
        self._stamp('date_started')

    def hold(self):
        """A work order in progress is put on hold."""
        self._check_state({'in_progress'}, _("put on hold"))
        self._set_state('on_hold')

    def resume(self):
        """A work order on hold goes back in progress; the hold reason no longer applies."""
        self._check_state({'on_hold'}, _("resumed"))
        self._set_state('in_progress')
        self._clear('hold_reason')

    def finish(self):
        """A work order in progress is done; the finish time is recorded."""
        self._check_state({'in_progress'}, _("finished"))
        self._set_state('done')
        self._stamp('date_done')

    # FA steps: the form buttons call these.

    def action_start(self):
        """Work order flow step: Planned -> In Progress."""
        self.start()

    def action_hold(self):
        """Work order flow step: In Progress -> On Hold."""
        self.hold()

    def action_resume(self):
        """Work order flow step: On Hold -> In Progress."""
        self.resume()

    def action_done(self):
        """Work order flow step: In Progress -> Done."""
        self.finish()
