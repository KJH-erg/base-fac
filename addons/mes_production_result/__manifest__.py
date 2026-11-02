{
    'name': 'MES Production Results',
    'version': '20.0.1.0.0',
    'summary': 'Record good and defect quantities and times by step, against the plan',
    'category': 'Manufacturing',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['mes_planning'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/mes_production_result_views.xml',
        'views/mes_production_plan_views.xml',
    ],
}
