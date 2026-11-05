# 상태·판정 등 보호된 필드는 이 모듈 코드에서만 바꿀 수 있도록 하는 내부 토큰.
# 컨텍스트에 이 객체 자체가 들어 있어야 하므로 RPC(JSON)로는 흉내낼 수 없다.
_INTERNAL_WRITE_TOKEN = object()
_TOKEN_KEY = 'mes_qc_internal_write'

GROUP_INSPECTOR = 'mes_quality_check.group_mes_qc_inspector'
GROUP_MANAGER = 'mes_quality_check.group_mes_qc_manager'


def internal_env(records):
    """보호된 필드를 쓸 수 있는 컨텍스트를 붙인 레코드셋을 돌려준다."""
    return records.with_context(**{_TOKEN_KEY: _INTERNAL_WRITE_TOKEN})


def is_internal(records):
    return records.env.context.get(_TOKEN_KEY) is _INTERNAL_WRITE_TOKEN


def is_manager(env):
    return env.user.has_group(GROUP_MANAGER)
