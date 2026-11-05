from odoo import fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mes_material_count = fields.Integer(
        string='공급 자재 수', compute='_compute_mes_material_count',
        groups='mes_material.group_mes_material_user')

    def _compute_mes_material_count(self):
        counts = dict(self.env['mes.material']._read_group(
            [('partner_id', 'in', self.ids)], ['partner_id'], ['__count']))
        for partner in self:
            partner.mes_material_count = counts.get(partner, 0)

    def action_view_mes_materials(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('mes_material.action_mes_material')
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'default_partner_id': self.id}
        action['display_name'] = _('공급 자재: %s', self.display_name)
        return action
