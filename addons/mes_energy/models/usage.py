import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# (사용량 필드, 입력 여부 필드)
VALUE_FIELDS = (('power_kwh', 'power_entered'), ('water_m3', 'water_entered'))
PROTECTED_FIELDS = ('power_exceeded', 'water_exceeded')


class MesEnergyUsage(models.Model):
    _name = 'mes.energy.usage'
    _description = '에너지 일일 사용량'
    _order = 'date desc, equipment_id'

    equipment_id = fields.Many2one(
        'mes.energy.equipment', string='설비', required=True, index=True, ondelete='restrict')
    date = fields.Date(string='날짜', required=True, index=True,
                       default=lambda self: fields.Date.context_today(self) - timedelta(days=1))
    month = fields.Char(string='연월', compute='_compute_month', store=True, index=True)

    power_kwh = fields.Float(string='전력 사용량(kWh)', digits=(16, 3))
    power_entered = fields.Boolean(
        string='전력 입력됨',
        help='체크되지 않으면 전력 사용량은 입력되지 않은 상태(빈 값)입니다. 0도 정상적인 사용량입니다.')
    water_m3 = fields.Float(string='용수 사용량(㎥)', digits=(16, 3))
    water_entered = fields.Boolean(
        string='용수 입력됨',
        help='체크되지 않으면 용수 사용량은 입력되지 않은 상태(빈 값)입니다. 0도 정상적인 사용량입니다.')

    power_exceeded = fields.Boolean(string='전력 초과', readonly=True, copy=False)
    water_exceeded = fields.Boolean(string='용수 초과', readonly=True, copy=False)
    is_exceeded = fields.Boolean(string='초과일', compute='_compute_is_exceeded', store=True)

    input_source = fields.Selection(
        [('manual', '화면 입력'), ('import', '파일 가져오기'), ('auto', '자동 처리')],
        string='입력 경로', required=True, default='manual', readonly=True)
    is_missing = fields.Boolean(string='누락', compute='_compute_is_missing', store=True,
                                help='전력·용수 중 하나라도 비어 있는 기록')
    is_closed = fields.Boolean(string='마감됨', compute='_compute_is_closed')

    _equipment_date_uniq = models.Constraint(
        'unique(equipment_id, date)',
        '같은 설비·날짜의 기록이 이미 있습니다.',
    )
    _values_positive = models.Constraint(
        'CHECK(power_kwh >= 0 AND water_m3 >= 0)',
        '사용량은 음수일 수 없습니다.',
    )

    # ------------------------------------------------------------------
    # compute
    # ------------------------------------------------------------------
    @api.depends('equipment_id', 'date')
    def _compute_display_name(self):
        for usage in self:
            usage.display_name = '%s %s' % (
                usage.equipment_id.display_name or '', fields.Date.to_string(usage.date) or '')

    @api.depends('date')
    def _compute_month(self):
        for usage in self:
            usage.month = usage.date.strftime('%Y-%m') if usage.date else False

    @api.depends('power_exceeded', 'water_exceeded')
    def _compute_is_exceeded(self):
        for usage in self:
            usage.is_exceeded = usage.power_exceeded or usage.water_exceeded

    @api.depends('power_entered', 'water_entered')
    def _compute_is_missing(self):
        for usage in self:
            usage.is_missing = not (usage.power_entered and usage.water_entered)

    @api.depends('month')
    def _compute_is_closed(self):
        closed = self._closed_months(set(self.mapped('month')))
        for usage in self:
            usage.is_closed = bool(usage.month) and usage.month in closed

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @api.model
    def _closed_months(self, months):
        months = [m for m in months if m]
        if not months:
            return set()
        return set(self.env['mes.energy.month.close'].sudo().search(
            [('name', 'in', months)]).mapped('name'))

    @api.model
    def _is_date_closed(self, date):
        date = fields.Date.to_date(date)
        return bool(date) and bool(self._closed_months({date.strftime('%Y-%m')}))

    @api.model
    def _today(self):
        return fields.Date.context_today(self)

    @api.model
    def _normalize_vals(self, vals, creating=False):
        """입력 여부와 사용량 값을 맞춘다. vals를 직접 고친다."""
        for protected in PROTECTED_FIELDS:
            vals.pop(protected, None)
        for value_field, entered_field in VALUE_FIELDS:
            # 주의: 0.0 == False 이므로 `in (None, False)`를 쓰면 0을 빈 값으로 오인한다.
            if value_field in vals and (vals[value_field] is None or vals[value_field] is False):
                vals[value_field] = 0.0
                if entered_field not in vals:
                    vals[entered_field] = False
            if entered_field in vals:
                if not vals[entered_field]:
                    vals[entered_field] = False
                    vals[value_field] = 0.0
            elif value_field in vals:
                vals[entered_field] = True
            elif creating:
                vals[entered_field] = False
        return vals

    def _evaluate_exceedance(self):
        """설비 기준에 따라 전력·용수 초과 여부를 판정한다.

        기준이 0이거나 값이 비어 있으면 그 항목은 초과가 아니다.
        """
        for usage in self:
            equipment = usage.equipment_id
            power = bool(
                usage.power_entered and equipment.power_limit > 0
                and float_compare(usage.power_kwh, equipment.power_limit, precision_digits=6) > 0)
            water = bool(
                usage.water_entered and equipment.water_limit > 0
                and float_compare(usage.water_m3, equipment.water_limit, precision_digits=6) > 0)
            if usage.power_exceeded != power or usage.water_exceeded != water:
                # 판정 결과 필드는 공개 write()에서 막혀 있으므로 상위 write로 직접 기록한다.
                super(MesEnergyUsage, usage).write({'power_exceeded': power, 'water_exceeded': water})

    def _check_equipment_active(self, equipment_id):
        equipment = self.env['mes.energy.equipment'].with_context(active_test=False).browse(equipment_id)
        if equipment.exists() and not equipment.active:
            raise UserError('사용 중이 아닌 설비(%s)로는 기록을 만들 수 없습니다.' % equipment.display_name)

    def _check_not_closed(self):
        closed = self._closed_months(set(self.mapped('month')))
        if closed:
            raise UserError('마감된 달(%s)의 기록은 만들거나 수정하거나 삭제할 수 없습니다.'
                            % ', '.join(sorted(closed)))

    # ------------------------------------------------------------------
    # constraints
    # ------------------------------------------------------------------
    @api.constrains('date')
    def _check_date_not_future(self):
        today = self._today()
        for usage in self:
            if usage.date and usage.date > today:
                raise ValidationError('오늘 이후 날짜(%s)의 기록은 만들 수 없습니다.' % usage.date)

    @api.constrains('power_kwh', 'water_m3')
    def _check_values_positive(self):
        for usage in self:
            if usage.power_kwh < 0 or usage.water_m3 < 0:
                raise ValidationError('사용량은 음수일 수 없습니다.')

    # ------------------------------------------------------------------
    # onchange
    # ------------------------------------------------------------------
    @api.onchange('power_kwh')
    def _onchange_power_kwh(self):
        # 0이 아닌 값을 넣으면 입력된 것으로 본다. 0을 기록하려면 '입력됨'을 직접 체크한다.
        # (새 기록 화면을 처음 열 때도 onchange가 불리므로 0일 때는 건드리지 않는다.)
        if self.power_kwh:
            self.power_entered = True

    @api.onchange('water_m3')
    def _onchange_water_m3(self):
        if self.water_m3:
            self.water_entered = True

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalize_vals(vals, creating=True)
            if vals.get('equipment_id'):
                self._check_equipment_active(vals['equipment_id'])
            if vals.get('date') and self._is_date_closed(vals['date']):
                raise UserError('마감된 달(%s)에는 기록을 만들 수 없습니다.'
                                % fields.Date.to_date(vals['date']).strftime('%Y-%m'))
        records = super().create(vals_list)
        records._evaluate_exceedance()
        return records

    def write(self, vals):
        vals = self._normalize_vals(dict(vals))
        if not vals:
            return True
        self._check_not_closed()
        if vals.get('date') and self._is_date_closed(vals['date']):
            raise UserError('마감된 달(%s)로 기록을 옮길 수 없습니다.'
                            % fields.Date.to_date(vals['date']).strftime('%Y-%m'))
        if vals.get('equipment_id'):
            changed = self.filtered(lambda u: u.equipment_id.id != vals['equipment_id'])
            if changed:
                changed._check_equipment_active(vals['equipment_id'])
        if 'input_source' not in vals and any(f in vals for pair in VALUE_FIELDS for f in pair):
            vals['input_source'] = 'manual'
        res = super().write(vals)
        if any(f in vals for f in ('equipment_id', 'power_kwh', 'power_entered', 'water_m3', 'water_entered')):
            self._evaluate_exceedance()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_closed(self):
        self._check_not_closed()

    # ------------------------------------------------------------------
    # 자동 처리
    # ------------------------------------------------------------------
    @api.model
    def _cron_create_missing_records(self):
        """사용 중인 설비 중 전날 기록이 없는 설비에 누락(빈) 기록을 만든다."""
        tz = self.env.context.get('tz') or self.env.user.tz
        if not tz:
            admin = self.env.ref('base.user_admin', raise_if_not_found=False)
            tz = (admin and admin.tz) or 'UTC'
        yesterday = fields.Date.context_today(self.with_context(tz=tz)) - timedelta(days=1)
        if self._is_date_closed(yesterday):
            _logger.info('mes_energy: %s is in a closed month, no missing records created', yesterday)
            return
        equipments = self.env['mes.energy.equipment'].search([('active', '=', True)])
        existing = self.search([('date', '=', yesterday), ('equipment_id', 'in', equipments.ids)]).equipment_id
        todo = equipments - existing
        if todo:
            self.create([{
                'equipment_id': equipment.id,
                'date': yesterday,
                'power_entered': False,
                'water_entered': False,
                'input_source': 'auto',
            } for equipment in todo])
