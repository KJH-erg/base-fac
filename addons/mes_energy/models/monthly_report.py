from odoo import fields, models, tools


class MesEnergyMonthly(models.Model):
    _name = 'mes.energy.monthly'
    _description = '에너지 월별 보기'
    _auto = False
    _order = 'month desc, equipment_id'

    month = fields.Char(string='연월', readonly=True)
    month_date = fields.Date(string='월', readonly=True)
    equipment_id = fields.Many2one('mes.energy.equipment', string='설비', readonly=True)
    power_total = fields.Float(string='전력 합계(kWh)', digits=(16, 3), readonly=True)
    water_total = fields.Float(string='용수 합계(㎥)', digits=(16, 3), readonly=True)
    exceeded_days = fields.Integer(string='초과일 수', readonly=True)
    missing_count = fields.Integer(string='누락 수', readonly=True)
    record_count = fields.Integer(string='기록 수', readonly=True)
    is_closed = fields.Boolean(string='마감됨', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    MIN(u.id) AS id,
                    u.month AS month,
                    date_trunc('month', u.date)::date AS month_date,
                    u.equipment_id AS equipment_id,
                    SUM(CASE WHEN u.power_entered THEN u.power_kwh ELSE 0 END) AS power_total,
                    SUM(CASE WHEN u.water_entered THEN u.water_m3 ELSE 0 END) AS water_total,
                    SUM(CASE WHEN u.is_exceeded THEN 1 ELSE 0 END) AS exceeded_days,
                    SUM(CASE WHEN u.is_missing THEN 1 ELSE 0 END) AS missing_count,
                    COUNT(*) AS record_count,
                    (c.id IS NOT NULL) AS is_closed
                FROM mes_energy_usage u
                LEFT JOIN mes_energy_month_close c ON c.name = u.month
                GROUP BY u.month, date_trunc('month', u.date), u.equipment_id, c.id
            )
        """ % self._table)
