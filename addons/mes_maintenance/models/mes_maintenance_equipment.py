from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

GROUP_TECHNICIAN = 'mes_maintenance.group_mes_maintenance_technician'


def _technician_domain(model):
    group = model.env.ref(GROUP_TECHNICIAN, raise_if_not_found=False)
    return [('share', '=', False), ('all_group_ids', 'in', group.ids if group else [])]


class MesMaintenanceEquipment(models.Model):
    _name = 'mes.maintenance.equipment'
    _description = '설비'
    _order = 'code, id'
    _rec_names_search = ['code', 'name']

    code = fields.Char('코드', required=True)
    name = fields.Char('이름', required=True)
    location = fields.Char('위치')
    technician_id = fields.Many2one(
        'res.users', string='담당 정비원', ondelete='restrict',
        domain=lambda self: _technician_domain(self))
    preventive_interval = fields.Integer('예방 정비 주기(일)', default=0,
                                         help='0이면 예방 정비를 하지 않습니다.')
    next_preventive_date = fields.Date('다음 예방 정비 예정일')
    request_ids = fields.One2many('mes.maintenance.request', 'equipment_id', string='정비 요청')
    request_count = fields.Integer('정비 요청 수', compute='_compute_request_count')
    maintenance_count = fields.Integer('누적 정비 횟수', compute='_compute_maintenance_totals', store=True)
    maintenance_cost = fields.Monetary('누적 비용', compute='_compute_maintenance_totals', store=True,
                                       currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='통화', compute='_compute_currency_id')
    active = fields.Boolean('사용', default=True)

    _code_unique = models.Constraint('UNIQUE(code)', '같은 설비 코드가 이미 있습니다.')
    _preventive_interval_positive = models.Constraint(
        'CHECK(preventive_interval >= 0)', '예방 정비 주기는 음수일 수 없습니다.')

    def _compute_display_name(self):
        for equipment in self:
            equipment.display_name = f'[{equipment.code}] {equipment.name}' if equipment.code else equipment.name

    def _compute_currency_id(self):
        for equipment in self:
            equipment.currency_id = self.env.company.currency_id

    @api.depends('request_ids')
    def _compute_request_count(self):
        counts = dict(self.env['mes.maintenance.request']._read_group(
            [('equipment_id', 'in', self.ids)], ['equipment_id'], ['__count']))
        for equipment in self:
            equipment.request_count = counts.get(equipment, 0)

    @api.depends('request_ids.state', 'request_ids.total_cost')
    def _compute_maintenance_totals(self):
        for equipment in self:
            done = equipment.request_ids.filtered(lambda r: r.state == 'done')
            equipment.maintenance_count = len(done)
            equipment.maintenance_cost = sum(done.mapped('total_cost'))

    @api.constrains('preventive_interval', 'next_preventive_date')
    def _check_preventive(self):
        for equipment in self:
            if equipment.preventive_interval > 0 and not equipment.next_preventive_date:
                raise ValidationError(
                    f'설비 {equipment.display_name}: 예방 정비 주기가 있으면 다음 예방 정비 예정일을 입력해야 합니다.')

    @api.constrains('technician_id')
    def _check_technician(self):
        group = self.env.ref(GROUP_TECHNICIAN)
        for equipment in self:
            if equipment.technician_id and group not in equipment.technician_id.sudo().all_group_ids:
                raise ValidationError('담당 정비원은 정비원 그룹의 사용자여야 합니다.')

    @api.ondelete(at_uninstall=False)
    def _unlink_except_has_requests(self):
        Request = self.env['mes.maintenance.request'].sudo().with_context(active_test=False)
        if Request.search_count([('equipment_id', 'in', self.ids)], limit=1):
            raise UserError('정비 요청이 있는 설비는 삭제할 수 없습니다. 사용 중지하세요.')

    def action_view_requests(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('mes_maintenance.action_mes_maintenance_request')
        action['domain'] = [('equipment_id', '=', self.id)]
        action['context'] = {'default_equipment_id': self.id}
        return action

    @api.model
    def _cron_create_preventive_requests(self):
        today = fields.Date.context_today(self)
        equipments = self.search([
            ('active', '=', True),
            ('preventive_interval', '>', 0),
            ('next_preventive_date', '!=', False),
            ('next_preventive_date', '<=', today),
        ])
        Request = self.env['mes.maintenance.request'].sudo()
        open_requests = Request.search([
            ('equipment_id', 'in', equipments.ids),
            ('maintenance_type', '=', 'preventive'),
            ('state', 'not in', ('done', 'rejected')),
        ])
        busy = open_requests.equipment_id
        group = self.env.ref(GROUP_TECHNICIAN)
        vals_list = []
        for equipment in equipments - busy:
            technician = equipment.technician_id
            if technician and group not in technician.sudo().all_group_ids:
                technician = technician.browse()
            vals_list.append({
                'equipment_id': equipment.id,
                'maintenance_type': 'preventive',
                'priority': 'normal',
                'technician_id': technician.id,
                'symptom': f'예방 정비 (예정일: {equipment.next_preventive_date})',
            })
        if vals_list:
            Request.create(vals_list)
        return True

    def _update_next_preventive_date(self, done_date):
        for equipment in self.sudo():
            if equipment.preventive_interval > 0:
                equipment.next_preventive_date = done_date + timedelta(days=equipment.preventive_interval)
