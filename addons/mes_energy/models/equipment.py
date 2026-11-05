from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class MesEnergyEquipment(models.Model):
    _name = 'mes.energy.equipment'
    _description = '에너지 설비'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='코드', required=True, index=True)
    name = fields.Char(string='이름', required=True)
    location = fields.Char(string='위치')
    power_limit = fields.Float(
        string='일일 전력 기준(kWh)', digits=(16, 3), default=0.0,
        help='일일 전력 사용량이 이 값보다 크면 초과입니다. 0이면 전력은 판정하지 않습니다.')
    water_limit = fields.Float(
        string='일일 용수 기준(㎥)', digits=(16, 3), default=0.0,
        help='일일 용수 사용량이 이 값보다 크면 초과입니다. 0이면 용수는 판정하지 않습니다.')
    active = fields.Boolean(string='사용 여부', default=True)
    usage_ids = fields.One2many('mes.energy.usage', 'equipment_id', string='일일 사용량')
    usage_count = fields.Integer(string='일일 사용량 수', compute='_compute_usage_count')

    _code_uniq = models.Constraint(
        'unique(code)',
        '설비 코드는 중복될 수 없습니다.',
    )
    _limits_positive = models.Constraint(
        'CHECK(power_limit >= 0 AND water_limit >= 0)',
        '사용량 기준은 음수일 수 없습니다.',
    )

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for equipment in self:
            if equipment.code:
                equipment.display_name = '[%s] %s' % (equipment.code, equipment.name or '')
            else:
                equipment.display_name = equipment.name or ''

    def _compute_usage_count(self):
        counts = dict(self.env['mes.energy.usage']._read_group(
            [('equipment_id', 'in', self.ids)], ['equipment_id'], ['__count']))
        for equipment in self:
            equipment.usage_count = counts.get(equipment, 0)

    @api.constrains('power_limit', 'water_limit')
    def _check_limits(self):
        for equipment in self:
            if equipment.power_limit < 0 or equipment.water_limit < 0:
                raise ValidationError('사용량 기준은 음수일 수 없습니다.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if isinstance(vals.get('code'), str):
                vals['code'] = vals['code'].strip()
        return super().create(vals_list)

    def write(self, vals):
        if isinstance(vals.get('code'), str):
            vals = dict(vals, code=vals['code'].strip())
        res = super().write(vals)
        if 'power_limit' in vals or 'water_limit' in vals:
            # 기준이 바뀌면 마감되지 않은 달의 기록만 새 기준으로 다시 판정한다.
            usages = self.env['mes.energy.usage'].search([('equipment_id', 'in', self.ids)])
            closed = usages._closed_months(set(usages.mapped('month')))
            usages.filtered(lambda u: u.month not in closed)._evaluate_exceedance()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_has_usage(self):
        if self.env['mes.energy.usage'].sudo().search_count([('equipment_id', 'in', self.ids)], limit=1):
            raise UserError('일일 사용량이 있는 설비는 삭제할 수 없습니다. 대신 사용 중지(보관)하세요.')

    def action_view_usages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '일일 사용량',
            'res_model': 'mes.energy.usage',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': {'default_equipment_id': self.id},
        }
