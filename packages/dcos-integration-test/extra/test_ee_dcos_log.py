import logging
import uuid

import pytest

import requests

from ee_helpers import dcos_config


log = logging.getLogger(__name__)

strict_only = pytest.mark.skipif(dcos_config['security'] != 'strict',
                                 reason='Tests must have to run on a cluster in strict mode')
pytestmark = [strict_only, pytest.mark.usefixtures("iam_verify_and_reset")]


def test_fine_grained_acls(cluster, peter_cluster):
    test_uuid = uuid.uuid4().hex

    task_id = "integration-test-task-logs-{}".format(test_uuid)

    task_definition = {
        "id": "/{}".format(task_id),
        "cpus": 0.1,
        "instances": 1,
        "mem": 128,
        "cmd": "echo STDOUT_LOG; echo STDERR_LOG >&2;sleep 999"
    }

    with cluster.marathon.deploy_and_cleanup(task_definition, check_health=False):
        url = get_task_url(cluster, task_id)
        task_stdout_response = cluster.get(url)
        check_response_ok(task_stdout_response)
        task_stdout = task_stdout_response.content.decode('utf-8', 'ignore')
        assert 'STDOUT_LOG' in task_stdout, 'Missing `STDOUT_LOG` in response. Got {}'.format(task_stdout)

        peter_response = peter_cluster.get(url)
        assert peter_response.status_code == 403, 'Peter should not be able to read superuser logs'


def test_system_logs(cluster, peter_cluster):
    """ test system level logs. Only superuser or anyone with dcos:adminrouter:ops:system-logs must be able to
        access the logs.
    """
    range_endpoint = 'v1/range/?limit=1'
    stream_endpoint = 'v1/stream/?skip_prev=1'

    for node in cluster.masters + cluster.all_slaves:
        response = cluster.logs.get(range_endpoint, node=node)
        check_response_ok(response)

        response = cluster.logs.get(stream_endpoint, node=node, stream=True)
        check_response_ok(response)

        peter_response = peter_cluster.logs.get(range_endpoint, node=node)
        assert peter_response.status_code == 403, 'Peter should not be able to get system logs'

        peter_response = peter_cluster.logs.get(stream_endpoint, node=node, stream=True)
        assert peter_response.status_code == 403, 'Peter should not be able to get system logs'


def check_response_ok(response: requests.models.Response):
    assert response.ok, 'Request {} returned response code {}'.format(response.url, response.status_code)


def get_task_url(cluster, task_name, stream=False):
    """ The function returns a logging URL for a given task
    :param cluster: cluster fixture
    :param task_name: task name
    :param stream: use range or stream endpoint
    :return: url to get the logs for a task
    """
    state_response = cluster.get('/mesos/state')
    check_response_ok(state_response)

    framework_id = None
    executor_id = None
    slave_id = None
    container_id = None

    state_response_json = state_response.json()
    assert 'frameworks' in state_response_json, 'Missing field `framework` in {}'.format(state_response_json)
    assert isinstance(state_response_json['frameworks'], list), '`framework` must be list. Got {}'.format(
        state_response_json)

    for framework in state_response_json['frameworks']:
        assert 'name' in framework, 'Missing field `name` in `frameworks`. Got {}'.format(state_response_json)
        # search for marathon framework
        if framework['name'] != 'marathon':
            continue

        assert 'tasks' in framework, 'Missing field `tasks`. Got {}'.format(state_response_json)
        assert isinstance(framework['tasks'], list), '`tasks` must be list. Got {}'.format(state_response_json)
        for task in framework['tasks']:
            assert 'id' in task, 'Missing field `id` in task. Got {}'.format(state_response_json)
            if not task['id'].startswith(task_name):
                continue

            assert 'framework_id' in task, 'Missing `framework_id` in task. Got {}'.format(state_response_json)
            assert 'executor_id' in task, 'Missing `executor_id` in task. Got {}'.format(state_response_json)
            assert 'id' in task, 'Missing `id` in task. Got {}'.format(state_response_json)
            assert 'slave_id' in task, 'Missing `slave_id` in task. Got {}'.format(state_response_json)

            framework_id = task['framework_id']
            # if task['executor_id'] is empty, we should use task['id']
            executor_id = task['executor_id']
            if not executor_id:
                executor_id = task['id']
            slave_id = task['slave_id']

            statuses = task.get('statuses')
            assert isinstance(statuses, list), 'Invalid field `statuses`. Got {}'.format(state_response_json)
            assert len(statuses) == 1, 'Must have only one status TASK_RUNNING. Got {}'.format(state_response_json)
            status = statuses[0]
            container_status = status.get('container_status')
            assert container_status
            container_id_field = container_status.get('container_id')
            assert container_id_field

            # traverse nested container_id fields
            container_ids = []
            while True:
                value = container_id_field.get('value')
                assert value
                container_ids.append(value)

                if 'parent' not in container_id_field:
                    break

                container_id_field = container_id_field['parent']
            container_id = '.'.join(reversed(container_ids))
            assert container_id

    # validate all required fields
    assert slave_id, 'Missing slave_id'
    assert framework_id, 'Missing framework_id'
    assert executor_id, 'Missing executor_id'
    assert container_id, 'Missing container_id'

    endpoint_type = 'range'
    if stream:
        endpoint_type = 'stream'
    return '/system/v1/agent/{}/logs/v1/{}/framework/{}/executor/{}/container/{}'.format(slave_id, endpoint_type,
                                                                                         framework_id, executor_id,
                                                                                         container_id)
