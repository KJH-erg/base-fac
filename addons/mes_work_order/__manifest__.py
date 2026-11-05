{
    'name': '작업지시',
    'version': '20.0.1.0.0',
    'category': 'Supply Chain',
    'summary': '작업지시 생성과 착수부터 완료까지의 진행 상태 관리',
    'description': """
작업지시를 만들고 확정, 착수, 보류, 재개, 완료, 취소까지 진행 상태를 관리한다.
공정 단계별 완료 표시, 진행률, 지연 자동 표시, 일괄 담당자 지정을 제공한다.
""",
    'depends': ['base'],
    'data': [
        'security/mes_work_order_security.xml',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'views/mes_work_order_views.xml',
        'wizard/mes_work_order_assign_wizard_views.xml',
        'views/mes_work_order_menus.xml',
        'security/ir.access.csv',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
