{
    'name': 'MES Lot Trace',
    'version': '20.0.1.0.0',
    'summary': 'Trace a lot forward to what it went into and backward to what it was made from',
    'category': 'Manufacturing',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['mes_routing', 'stock'],
    'data': [
        'security/ir.access.csv',
        'views/mes_lot_trace_views.xml',
        'views/stock_lot_views.xml',
    ],
}
