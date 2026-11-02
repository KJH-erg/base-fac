from odoo.tests import TransactionCase


class TestMesLotTrace(TransactionCase):
    """raw lot -> semi-finished lot -> finished lot, through two real MOs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.group_user').write({'implied_ids': [(4, cls.env.ref('stock.group_production_lot').id)]})
        cls.stock_location = cls.env.ref('stock.warehouse0').lot_stock_id
        cls.raw = cls._product('Raw')
        cls.semi = cls._product('Semi')
        cls.finished = cls._product('Finished')
        cls.raw_lot = cls._lot('RAW-1', cls.raw)
        cls.other_lot = cls._lot('RAW-OTHER', cls.raw)
        cls.env['stock.quant']._update_available_quantity(cls.raw, cls.stock_location, 10, lot_id=cls.raw_lot)
        cls.semi_lot = cls._lot('SEMI-1', cls.semi)
        cls.finished_lot = cls._lot('FIN-1', cls.finished)
        cls._manufacture(cls.semi, cls.semi_lot, cls.raw)
        cls._manufacture(cls.finished, cls.finished_lot, cls.semi)

    @classmethod
    def _product(cls, name):
        return cls.env['product.product'].create({'name': name, 'is_storable': True, 'tracking': 'lot'})

    @classmethod
    def _lot(cls, name, product):
        return cls.env['stock.lot'].create({'name': name, 'product_id': product.id})

    @classmethod
    def _manufacture(cls, product, lot, component):
        bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'bom_line_ids': [(0, 0, {'product_id': component.id, 'product_qty': 1})],
        })
        production = cls.env['mrp.production'].create({
            'product_id': product.id, 'product_qty': 5, 'bom_id': bom.id, 'uom_id': product.uom_id.id,
        })
        production.action_confirm()
        production.action_assign()
        production.lot_producing_ids = lot
        production.qty_producing = 5
        production.move_raw_ids.picked = True
        production.button_mark_done()
        assert production.state == 'done'

    def test_backward_walks_to_raw_lot(self):
        rows = self.finished_lot._mes_trace('backward')
        self.assertEqual([(row['lot_id'], row['depth']) for row in rows],
                         [(self.semi_lot.id, 1), (self.raw_lot.id, 2)])
        self.assertEqual(rows[0]['quantity'], 5)
        self.assertEqual(rows[0]['production_id'], self.env['mrp.production'].search([('lot_producing_ids', 'in', self.finished_lot.id)]).id)

    def test_forward_walks_to_finished_lot(self):
        rows = self.raw_lot._mes_trace('forward')
        self.assertEqual([(row['lot_id'], row['depth']) for row in rows],
                         [(self.semi_lot.id, 1), (self.finished_lot.id, 2)])

    def test_unrelated_lot_has_no_trace(self):
        self.assertEqual(self.other_lot._mes_trace('forward'), [])
        self.assertEqual(self.raw_lot._mes_trace('backward'), [])

    def test_wizard_counts_both_directions(self):
        trace = self.env['mes.lot.trace'].create({'lot_id': self.semi_lot.id})
        trace.action_trace()
        self.assertEqual(trace.backward_count, 1)
        self.assertEqual(trace.forward_count, 1)
        self.assertEqual(trace.forward_on_hand, 5)
        trace.direction = 'forward'
        trace.action_trace()
        self.assertEqual(trace.backward_count, 0)
        self.assertEqual(trace.forward_count, 1)

    def test_lot_button_opens_filled_trace(self):
        action = self.finished_lot.action_open_mes_trace()
        trace = self.env['mes.lot.trace'].browse(action['res_id'])
        self.assertEqual(len(trace.line_ids), 2)
