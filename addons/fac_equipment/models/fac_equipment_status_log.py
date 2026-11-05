from odoo import fields, models

from .fac_equipment import STATES


class FacEquipmentStatusLog(models.Model):
    _name = 'fac.equipment.status.log'
    _description = 'Equipment Status History'
    _order = 'changed_on desc, id desc'

    equipment_id = fields.Many2one('fac.equipment', string='Equipment', required=True,
                                   ondelete='cascade', index=True)
    old_state = fields.Selection(STATES, string='From')
    new_state = fields.Selection(STATES, string='To', required=True)
    changed_on = fields.Datetime(string='Changed On', required=True, default=fields.Datetime.now)
    changed_by_id = fields.Many2one('res.users', string='Changed By', required=True,
                                    default=lambda self: self.env.user)
    note = fields.Char(string='Note')
