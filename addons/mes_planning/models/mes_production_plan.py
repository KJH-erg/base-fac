from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MesProductionPlan(models.Model):
    _name = 'mes.production.plan'
    _description = 'MES Production Plan'
    _inherit = ['mail.thread']
    _order = 'date_planned desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, copy=False, tracking=True)
    date_planned = fields.Date(string='Planned Date', required=True, default=fields.Date.context_today, tracking=True, index=True)
    date_deadline = fields.Date(string='Deadline', tracking=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Line', required=True, check_company=True, tracking=True, index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True, check_company=True, tracking=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    qty = fields.Float(string='Planned Qty', required=True, default=1, tracking=True)
    routing_id = fields.Many2one(
        'mes.routing', string='Routing', check_company=True,
        domain="['|', ('product_tmpl_id', '=', False), ('product_tmpl_id.product_variant_ids', 'in', product_id)]")
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', copy=False, readonly=True, check_company=True)
    planned_minutes = fields.Float(compute='_compute_planned_minutes', store=True, help="Standard minutes on this line, from the routing.")
    capacity_minutes = fields.Float(compute='_compute_load', string='Daily Capacity (min)')
    load_percent = fields.Float(compute='_compute_load', string='Line Load %', help="All plans on this line and date, against its daily capacity.")
    is_late = fields.Boolean(compute='_compute_is_late', string='Misses Deadline')
    note = fields.Text()

    _qty_positive = models.Constraint('CHECK(qty > 0)', 'Planned quantity must be positive.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mes.production.plan') or _('New')
        return super().create(vals_list)

    @api.depends('qty', 'workcenter_id', 'routing_id.step_ids.workcenter_id',
                 'routing_id.step_ids.setup_minutes', 'routing_id.step_ids.cycle_minutes')
    def _compute_planned_minutes(self):
        for plan in self:
            plan.planned_minutes = plan.routing_id.minutes_for_qty(plan.qty, plan.workcenter_id) if plan.routing_id else 0

    @api.depends('workcenter_id.resource_calendar_id.hours_per_day', 'date_planned', 'planned_minutes', 'state')
    def _compute_load(self):
        planned = self.filtered(lambda plan: plan.workcenter_id and plan.date_planned)
        totals = {}
        if planned:
            groups = self.sudo()._read_group(
                [('workcenter_id', 'in', planned.workcenter_id.ids),
                 ('date_planned', 'in', planned.mapped('date_planned')),
                 ('state', '!=', 'cancel')],
                ['workcenter_id', 'date_planned:day'],
                ['planned_minutes:sum'],
            )
            totals = {(workcenter.id, fields.Date.to_date(day)): minutes for workcenter, day, minutes in groups}
        for plan in self:
            capacity = plan.workcenter_id.resource_calendar_id.hours_per_day * 60
            total = totals.get((plan.workcenter_id.id, plan.date_planned), 0)
            plan.capacity_minutes = capacity
            plan.load_percent = total / capacity * 100 if capacity else 0

    @api.depends('date_planned', 'date_deadline')
    def _compute_is_late(self):
        for plan in self:
            plan.is_late = bool(plan.date_deadline and plan.date_planned and plan.date_planned > plan.date_deadline)

    def action_confirm(self):
        self.filtered(lambda plan: plan.state == 'draft').write({'state': 'confirmed'})

    def action_done(self):
        self.filtered(lambda plan: plan.state == 'confirmed').write({'state': 'done'})

    def action_cancel(self):
        self.filtered(lambda plan: plan.state in ('draft', 'confirmed')).write({'state': 'cancel'})

    def action_draft(self):
        self.filtered(lambda plan: plan.state == 'cancel').write({'state': 'draft'})

    def action_create_production(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_("Only a confirmed plan can create a manufacturing order."))
        if self.production_id:
            raise UserError(_("This plan already has a manufacturing order."))
        bom = self.env['mrp.bom']._bom_find(self.product_id, company_id=self.company_id.id)[self.product_id]
        self.production_id = self.env['mrp.production'].create({
            'product_id': self.product_id.id,
            'product_qty': self.qty,
            'uom_id': self.uom_id.id,
            'bom_id': bom.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'date_start': fields.Datetime.to_datetime(self.date_planned),
        })
        return self.action_open_production()

    def action_open_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': self.production_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
