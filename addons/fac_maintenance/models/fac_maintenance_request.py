from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

STATES = [
    ('requested', 'Requested'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
    ('cancelled', 'Cancelled'),
]

MAINTENANCE_TYPES = [
    ('corrective', 'Corrective'),
    ('preventive', 'Preventive'),
]


class FacMaintenanceRequest(models.Model):
    _name = 'fac.maintenance.request'
    _description = 'Maintenance Request'
    _order = 'request_date desc, id desc'

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    title = fields.Char(string='Subject', required=True)
    # Equipment is referenced by name/code text only; no link to another FAC's model.
    equipment_ref = fields.Char(string='Equipment', required=True, help="Equipment name or code")
    maintenance_type = fields.Selection(MAINTENANCE_TYPES, string='Type', required=True, default='corrective')
    requested_by_id = fields.Many2one('res.users', string='Requested By', default=lambda self: self.env.user)
    technician_id = fields.Many2one('res.users', string='Technician')
    request_date = fields.Datetime(string='Requested On', required=True, default=fields.Datetime.now)
    date_started = fields.Datetime(string='Started On', readonly=True, copy=False)
    date_done = fields.Datetime(string='Finished On', readonly=True, copy=False)
    duration_hours = fields.Float(string='Duration (h)', compute='_compute_duration_hours', store=True)
    problem_description = fields.Text(string='Problem')
    work_description = fields.Text(string='Work Done', copy=False)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)
    cost = fields.Monetary(string='Cost', currency_field='currency_id', copy=False)
    state = fields.Selection(STATES, string='Status', required=True, default='requested',
                             readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') != 'New':
                continue
            number = self.env['ir.sequence'].next_by_code('fac.maintenance.request')
            if number:
                vals['name'] = number
        return super().create(vals_list)

    # EB: execution steps without business meaning of their own.

    @api.depends('date_started', 'date_done')
    def _compute_duration_hours(self):
        for request in self:
            if request.date_started and request.date_done:
                delta = request.date_done - request.date_started
                request.duration_hours = delta.total_seconds() / 3600.0
            else:
                request.duration_hours = 0.0

    @api.constrains('cost')
    def _check_cost(self):
        for request in self:
            if request.cost < 0:
                raise ValidationError(_("Maintenance cost cannot be negative."))

    def _check_state(self, allowed_states, action_label):
        """Raise if any record is not in one of allowed_states."""
        for request in self:
            if request.state not in allowed_states:
                raise UserError(_(
                    "Maintenance request %(name)s cannot be %(action)s while it is %(state)s.",
                    name=request.name, action=action_label,
                    state=dict(STATES)[request.state],
                ))

    def _require_value(self, field_name, message):
        """Raise message (with %(name)s) for the first record whose field_name is empty."""
        for request in self:
            if not request[field_name]:
                raise UserError(message % {'name': request.name})

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
        """A requested job with a technician goes in progress; the start time is recorded."""
        self._check_state({'requested'}, _("started"))
        self._require_value('technician_id', _("Assign a technician before starting %(name)s."))
        self._set_state('in_progress')
        self._stamp('date_started')

    def finish(self):
        """A job in progress whose work is described is done; the finish time is recorded."""
        self._check_state({'in_progress'}, _("finished"))
        self._require_value('work_description', _("Describe the work done before finishing %(name)s."))
        self._set_state('done')
        self._stamp('date_done')

    def cancel(self):
        """A requested job or a job in progress may be cancelled."""
        self._check_state({'requested', 'in_progress'}, _("cancelled"))
        self._set_state('cancelled')

    def reopen(self):
        """A cancelled job is requested again; its earlier start time no longer applies."""
        self._check_state({'cancelled'}, _("reopened"))
        self._set_state('requested')
        self._clear('date_started')

    # FA steps: the form buttons call these.

    def action_start(self):
        """Maintenance flow step: Requested -> In Progress."""
        self.start()

    def action_done(self):
        """Maintenance flow step: In Progress -> Done."""
        self.finish()

    def action_cancel(self):
        """Maintenance flow step: Requested / In Progress -> Cancelled."""
        self.cancel()

    def action_reopen(self):
        """Maintenance flow step: Cancelled -> Requested."""
        self.reopen()
