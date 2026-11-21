"""Pure, sealed FoundValue worker policy and initial child-environment helpers.

No CPU, environment, file, SDK or native process is read by this module.
Zero selects the existing original scalar dispatcher, not the batch API.
"""
from collections.abc import Mapping

POLICY_FIELD = 'found_value_worker_policy'
POLICY_SCHEMA = 'zerosis.found_value_worker_policy.v1'
REQUESTED_VALUES = ('auto', '0', '1', '2', '4')
WORKER_VALUES = (0, 1, 2, 4)
CPU_SOURCES = ('process_cpu_count', 'cpu_count', 'unavailable', 'explicit', 'legacy_request')
ENVIRONMENT_NAMES = frozenset(('ZEROSIS_FOUND_VALUE_WORKERS', 'ZEROSIS_FOUND_VALUE_TRACE',
                               'ZEROSIS_FOUND_VALUE_CPU_TRACE'))


def _require(value, message):
    if not value:
        raise ValueError(message)


def _hint(count, source):
    _require(type(source) is str and source in CPU_SOURCES, 'Unknown logical CPU hint source')
    _require(count is None or (type(count) is int and count >= 0), 'Logical CPU hint must be a nonnegative integer or None')
    _require(source != 'unavailable' or count is None, 'Unavailable CPU hint must be None')
    return {'source': source, 'available_logical_cpus': count}


def _resolved(count):
    return 0 if count is None or count <= 1 else 2 if count <= 3 else 4


def _record(requested, workers, hint):
    return {'schema': POLICY_SCHEMA, 'requested': requested, 'resolved_workers': workers,
            'cpu_hint': dict(hint), 'trace_enabled': False, 'cpu_trace_enabled': False}


def resolve_policy(requested, available_logical_cpus=None, cpu_source='unavailable'):
    """Resolve one preparation selection; callers provide any sampled CPU hint."""
    _require(type(requested) is str and requested in REQUESTED_VALUES,
             'FoundValue workers must be exactly auto, 0, 1, 2, or 4')
    hint = _hint(available_logical_cpus, cpu_source)
    if requested != 'auto':
        _require(available_logical_cpus is None and cpu_source in ('unavailable', 'explicit'),
                 'An explicit worker selection does not consume a CPU hint')
        return _record(requested, int(requested), _hint(None, 'explicit'))
    _require(cpu_source in ('process_cpu_count', 'cpu_count', 'unavailable'), 'Auto requires a logical CPU availability hint')
    return _record(requested, _resolved(available_logical_cpus), hint)


def validate_policy(value):
    """Validate the exact persisted contract and return an independent value copy."""
    fields = {'schema', 'requested', 'resolved_workers', 'cpu_hint', 'trace_enabled', 'cpu_trace_enabled'}
    _require(type(value) is dict and set(value) == fields, 'Malformed FoundValue worker policy fields')
    _require(type(value['schema']) is str and value['schema'] == POLICY_SCHEMA, 'Unknown FoundValue worker policy schema')
    requested, workers, hint = value['requested'], value['resolved_workers'], value['cpu_hint']
    _require(type(requested) is str and requested in REQUESTED_VALUES, 'Malformed FoundValue worker selection')
    _require(type(workers) is int and workers in WORKER_VALUES, 'Malformed resolved FoundValue worker count')
    _require(type(hint) is dict and set(hint) == {'source', 'available_logical_cpus'}, 'Malformed logical CPU hint fields')
    hint = _hint(hint['available_logical_cpus'], hint['source'])
    _require(value['trace_enabled'] is False and value['cpu_trace_enabled'] is False, 'Normal worker policy must keep both traces disabled')
    if requested == 'auto':
        _require(hint['source'] in ('process_cpu_count', 'cpu_count', 'unavailable') and
                 workers == _resolved(hint['available_logical_cpus']), 'Auto worker count differs from its sealed logical CPU hint')
    else:
        _require(workers == int(requested) and hint['available_logical_cpus'] is None and
                 hint['source'] in ('explicit', 'legacy_request'), 'Explicit worker count or hint differs')
        _require(hint['source'] != 'legacy_request' or requested == '0', 'A legacy request must remain original scalar zero')
    return _record(requested, workers, hint)


def policy_from_request(request):
    """Missing legacy metadata is scalar zero; malformed present metadata fails."""
    _require(type(request) is dict, 'Runtime request must be a dictionary')
    if POLICY_FIELD not in request:
        return _record('0', 0, _hint(None, 'legacy_request'))
    return validate_policy(request[POLICY_FIELD])


def driver_policy(policy_or_none, resolved_flag_or_none):
    """Bind an explicit resolved flag to sealed metadata before creating Host."""
    if policy_or_none is None:
        _require(resolved_flag_or_none is None or (type(resolved_flag_or_none) is str and resolved_flag_or_none == '0'),
                 'A legacy driver contract only permits original scalar zero')
        return policy_from_request({})
    policy = validate_policy(policy_or_none)
    _require(type(resolved_flag_or_none) is str and resolved_flag_or_none in ('0', '1', '2', '4') and
             int(resolved_flag_or_none) == policy['resolved_workers'], 'Driver worker flag differs from the sealed preparation policy')
    return policy


def child_environment(parent, policy):
    """Return a fresh environment; ignore all case variants of inherited knobs."""
    policy = validate_policy(policy)
    _require(isinstance(parent, Mapping), 'Parent environment must be a mapping')
    result = {}
    for name, value in parent.items():
        _require(type(name) is str and type(value) is str, 'Environment names and values must be strings')
        if name.upper() not in ENVIRONMENT_NAMES:
            result[name] = value
    result['ZEROSIS_FOUND_VALUE_WORKERS'] = str(policy['resolved_workers'])
    return result
