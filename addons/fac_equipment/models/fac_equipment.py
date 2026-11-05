from odoo import _, api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('available', 'Available'),
    ('in_use', 'In Use'),
    ('maintenance', 'Under Maintenance'),
    ('broken', 'Broken'),
]

# Allowed status changes: current state -> states it may move to.
ALLOWED_TRANSITIONS = {
    'available': {'in_use', 'maintenance', 'broken'},
    'in_use': {'available', 'maintenance', 'broken'},
    'maintenance': {'available', 'broken'},
    'broken': {'maintenance'},
}


class FacEquipment(models.Model):
    _name = 'fac.equipment'
    _description = 'Equipment'
    _order = 'code'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, copy=False)
    category = fields.Char(string='Category')
    location = fields.Char(string='Location')
    state = fields.Selection(STATES, string='Status', required=True, default='available',
                             readonly=True, copy=False)
    note = fields.Text(string='Notes')
    active = fields.Boolean(default=True)
    status_log_ids = fields.One2many('fac.equipment.status.log', 'equipment_id',
                                     string='Status History', readonly=True)
    status_log_count = fields.Integer(string='Status Changes', compute='_compute_status_log_count')

    _code_unique = models.Constraint('unique(code)', 'Equipment code must be unique.')

    # EB: execution steps without business meaning of their own.

    @api.depends('status_log_ids')
    def _compute_status_log_count(self):
        for equipment in self:
            equipment.status_log_count = len(equipment.status_log_ids)

    def _check_transition(self, new_state):
        """Raise if any record may not move to new_state."""
        labels = dict(STATES)
        for equipment in self:
            if new_state not in ALLOWED_TRANSITIONS[equipment.state]:
                raise UserError(_(
                    "Equipment %(code)s cannot change from %(old)s to %(new)s.",
                    code=equipment.code, old=labels[equipment.state], new=labels[new_state],
                ))

    def _log_status_change(self, new_state):
        """Write one history line per record, from its current status to new_state."""
        vals_list = [
            {'equipment_id': equipment.id, 'old_state': equipment.state, 'new_state': new_state}
            for equipment in self
        ]
        self.env['fac.equipment.status.log'].create(vals_list)

    def _set_state(self, new_state):
        """Write the new status."""
        self.write({'state': new_state})

    # BM: one business rule each. The history line is written before the status changes.

    def mark_available(self):
        """In-use or maintained equipment becomes available again."""
        self._check_transition('available')
        self._log_status_change('available')
        self._set_state('available')

    def mark_in_use(self):
        """Available equipment goes into use."""
        self._check_transition('in_use')
        self._log_status_change('in_use')
        self._set_state('in_use')

    def send_to_maintenance(self):
        """Equipment that is not under maintenance is sent to maintenance."""
        self._check_transition('maintenance')
        self._log_status_change('maintenance')
        self._set_state('maintenance')

    def report_broken(self):
        """Equipment that is not broken is reported broken."""
        self._check_transition('broken')
        self._log_status_change('broken')
        self._set_state('broken')

    # FA steps: the form buttons call these.

    def action_set_available(self):
        """Status flow step: release from use or bring back from maintenance."""
        self.mark_available()

    def action_set_in_use(self):
        """Status flow step: start using the equipment."""
        self.mark_in_use()

    def action_set_maintenance(self):
        """Status flow step: send the equipment to maintenance."""
        self.send_to_maintenance()

    def action_set_broken(self):
        """Status flow step: report the equipment as broken."""
        self.report_broken()

    # AC part: screen navigation.

    def action_view_status_log(self):
        """Open the status history of this equipment."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Status History'),
            'res_model': 'fac.equipment.status.log',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': {'default_equipment_id': self.id},
        }
