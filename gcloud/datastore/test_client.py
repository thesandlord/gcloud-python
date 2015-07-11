# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest2


def _make_entity_pb(dataset_id, kind, integer_id, name=None, str_val=None):
    from gcloud.datastore import _datastore_v1_pb2 as datastore_pb

    entity_pb = datastore_pb.Entity()
    entity_pb.key.partition_id.dataset_id = dataset_id
    path_element = entity_pb.key.path_element.add()
    path_element.kind = kind
    path_element.id = integer_id
    if name is not None and str_val is not None:
        prop = entity_pb.property.add()
        prop.name = name
        prop.value.string_value = str_val

    return entity_pb


class TestClient(unittest2.TestCase):

    DATASET_ID = 'DATASET'
    CONNECTION = object()

    def _getTargetClass(self):
        from gcloud.datastore.client import Client
        return Client

    def _makeOne(self, dataset_id=DATASET_ID, namespace=None,
                 connection=CONNECTION):
        return self._getTargetClass()(dataset_id=dataset_id,
                                      namespace=namespace,
                                      connection=connection)

    def test_ctor_w_dataset_id_no_environ(self):
        self.assertRaises(EnvironmentError, self._makeOne, None)

    def test_ctor_w_implicit_inputs(self):
        from gcloud._testing import _Monkey
        from gcloud.datastore import client as _MUT

        OTHER = 'other'
        conn = object()
        klass = self._getTargetClass()
        with _Monkey(_MUT,
                     _determine_default_dataset_id=lambda x: x or OTHER,
                     get_connection=lambda: conn):
            client = klass()
        self.assertEqual(client.dataset_id, OTHER)
        self.assertEqual(client.namespace, None)
        self.assertTrue(client.connection is conn)
        self.assertTrue(client.current_batch is None)
        self.assertTrue(client.current_transaction is None)

    def test_ctor_w_explicit_inputs(self):
        OTHER = 'other'
        NAMESPACE = 'namespace'
        conn = object()
        client = self._makeOne(dataset_id=OTHER,
                               namespace=NAMESPACE,
                               connection=conn)
        self.assertEqual(client.dataset_id, OTHER)
        self.assertEqual(client.namespace, NAMESPACE)
        self.assertTrue(client.connection is conn)
        self.assertTrue(client.current_batch is None)
        self.assertEqual(list(client._batch_stack), [])

    def test__push_batch_and__pop_batch(self):
        conn = object()
        client = self._makeOne(connection=conn)
        batch = client.batch()
        xact = client.transaction()
        client._push_batch(batch)
        self.assertEqual(list(client._batch_stack), [batch])
        self.assertTrue(client.current_batch is batch)
        self.assertTrue(client.current_transaction is None)
        client._push_batch(xact)
        self.assertTrue(client.current_batch is xact)
        self.assertTrue(client.current_transaction is xact)
        # list(_LocalStack) returns in reverse order.
        self.assertEqual(list(client._batch_stack), [xact, batch])
        self.assertTrue(client._pop_batch() is xact)
        self.assertEqual(list(client._batch_stack), [batch])
        self.assertTrue(client._pop_batch() is batch)
        self.assertEqual(list(client._batch_stack), [])

    def test_get_miss(self):
        _called_with = []

        def _get_multi(*args, **kw):
            _called_with.append((args, kw))
            return []

        connection = object()
        client = self._makeOne(connection=connection)
        client.get_multi = _get_multi

        key = object()

        self.assertTrue(client.get(key) is None)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['keys'], [key])
        self.assertTrue(_called_with[0][1]['missing'] is None)
        self.assertTrue(_called_with[0][1]['deferred'] is None)

    def test_get_hit(self):
        _called_with = []
        _entity = object()

        def _get_multi(*args, **kw):
            _called_with.append((args, kw))
            return [_entity]

        connection = object()
        client = self._makeOne(connection=connection)
        client.get_multi = _get_multi

        key, missing, deferred = object(), [], []

        self.assertTrue(client.get(key, missing, deferred) is _entity)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['keys'], [key])
        self.assertTrue(_called_with[0][1]['missing'] is missing)
        self.assertTrue(_called_with[0][1]['deferred'] is deferred)

    def test_get_multi_no_keys(self):
        connection = object()
        client = self._makeOne(connection=connection)
        results = client.get_multi([])
        self.assertEqual(results, [])

    def test_get_multi_miss(self):
        from gcloud.datastore.key import Key
        from gcloud.datastore.test_connection import _Connection

        connection = _Connection()
        client = self._makeOne(connection=connection)
        key = Key('Kind', 1234, dataset_id=self.DATASET_ID)
        results = client.get_multi([key])
        self.assertEqual(results, [])

    def test_get_multi_miss_w_missing(self):
        from gcloud.datastore import _datastore_v1_pb2 as datastore_pb
        from gcloud.datastore.key import Key
        from gcloud.datastore.test_connection import _Connection

        KIND = 'Kind'
        ID = 1234

        # Make a missing entity pb to be returned from mock backend.
        missed = datastore_pb.Entity()
        missed.key.partition_id.dataset_id = self.DATASET_ID
        path_element = missed.key.path_element.add()
        path_element.kind = KIND
        path_element.id = ID

        # Set missing entity on mock connection.
        connection = _Connection()
        connection._missing = [missed]
        client = self._makeOne(connection=connection)

        key = Key(KIND, ID, dataset_id=self.DATASET_ID)
        missing = []
        entities = client.get_multi([key], missing=missing)
        self.assertEqual(entities, [])
        self.assertEqual([missed.key.to_protobuf() for missed in missing],
                         [key.to_protobuf()])

    def test_get_multi_w_missing_non_empty(self):
        from gcloud.datastore.key import Key

        CONNECTION = object()
        client = self._makeOne(connection=CONNECTION)
        key = Key('Kind', 1234, dataset_id=self.DATASET_ID)

        missing = ['this', 'list', 'is', 'not', 'empty']
        self.assertRaises(ValueError, client.get_multi,
                          [key], missing=missing)

    def test_get_multi_w_deferred_non_empty(self):
        from gcloud.datastore.key import Key

        CONNECTION = object()
        client = self._makeOne(connection=CONNECTION)
        key = Key('Kind', 1234, dataset_id=self.DATASET_ID)

        deferred = ['this', 'list', 'is', 'not', 'empty']
        self.assertRaises(ValueError, client.get_multi,
                          [key], deferred=deferred)

    def test_get_multi_miss_w_deferred(self):
        from gcloud.datastore.key import Key
        from gcloud.datastore.test_connection import _Connection

        key = Key('Kind', 1234, dataset_id=self.DATASET_ID)

        # Set deferred entity on mock connection.
        connection = _Connection()
        connection._deferred = [key.to_protobuf()]
        client = self._makeOne(connection=connection)

        deferred = []
        entities = client.get_multi([key], deferred=deferred)
        self.assertEqual(entities, [])
        self.assertEqual([def_key.to_protobuf() for def_key in deferred],
                         [key.to_protobuf()])

    def _verifyProtobufCall(self, called_with, URI, conn):
        self.assertEqual(called_with['uri'], URI)
        self.assertEqual(called_with['method'], 'POST')
        self.assertEqual(called_with['headers']['Content-Type'],
                         'application/x-protobuf')
        self.assertEqual(called_with['headers']['User-Agent'],
                         conn.USER_AGENT)

    def test_get_multi_w_deferred_from_backend_but_not_passed(self):
        from gcloud.datastore import _datastore_v1_pb2 as datastore_pb
        from gcloud.datastore.connection import Connection
        from gcloud.datastore.key import Key
        from gcloud.datastore import test_connection

        # Shortening name, import line above was too long.
        cmp_key_after_req = test_connection._compare_key_pb_after_request

        key1 = Key('Kind', dataset_id=self.DATASET_ID)
        key2 = Key('Kind', 2345, dataset_id=self.DATASET_ID)
        key_pb1 = key1.to_protobuf()
        key_pb2 = key2.to_protobuf()

        # Build mock first response.
        rsp_pb1 = datastore_pb.LookupResponse()
        entity1 = datastore_pb.Entity()
        entity1.key.CopyFrom(key_pb1)
        # Add the entity to the "found" part of the response.
        rsp_pb1.found.add(entity=entity1)
        # Add the second key to the "deferred" part of the response.
        rsp_pb1.deferred.add().CopyFrom(key_pb2)

        # Build mock second response.
        rsp_pb2 = datastore_pb.LookupResponse()
        # Add in entity that was deferred.
        entity2 = datastore_pb.Entity()
        entity2.key.CopyFrom(key_pb2)
        rsp_pb2.found.add(entity=entity2)

        connection = Connection()
        client = self._makeOne(connection=connection)
        # Add mock http object to connection with response from above.
        http = connection._http = _HttpMultiple(
            ({'status': '200'}, rsp_pb1.SerializeToString()),
            ({'status': '200'}, rsp_pb2.SerializeToString()),
        )

        missing = []
        found = client.get_multi([key1, key2], missing=missing)
        self.assertEqual(len(found), 2)
        self.assertEqual(len(missing), 0)

        # Check the actual contents on the response.
        self.assertEqual(found[0].key.path, key1.path)
        self.assertEqual(found[0].key.dataset_id, key1.dataset_id)
        self.assertEqual(found[1].key.path, key2.path)
        self.assertEqual(found[1].key.dataset_id, key2.dataset_id)

        # Check that our http object was called correctly.
        cw = http._called_with
        rq_class = datastore_pb.LookupRequest
        request = rq_class()
        self.assertEqual(len(cw), 2)

        # Make URI to check for requests.
        URI = '/'.join([
            connection.api_base_url,
            'datastore',
            connection.API_VERSION,
            'datasets',
            self.DATASET_ID,
            'lookup',
        ])

        # Make sure the first called with argument checks out.
        self._verifyProtobufCall(cw[0], URI, connection)
        request.ParseFromString(cw[0]['body'])
        keys = list(request.key)
        self.assertEqual(len(keys), 2)
        cmp_key_after_req(self, key_pb1, keys[0])
        cmp_key_after_req(self, key_pb2, keys[1])

        # Make sure the second called with argument checks out.
        self._verifyProtobufCall(cw[1], URI, connection)
        request.ParseFromString(cw[1]['body'])
        keys = list(request.key)
        self.assertEqual(len(keys), 1)
        cmp_key_after_req(self, key_pb2, keys[0])

    def test_get_multi_hit(self):
        from gcloud.datastore.key import Key
        from gcloud.datastore.test_connection import _Connection

        KIND = 'Kind'
        ID = 1234
        PATH = [{'kind': KIND, 'id': ID}]

        # Make a found entity pb to be returned from mock backend.
        entity_pb = _make_entity_pb(self.DATASET_ID, KIND, ID, 'foo', 'Foo')

        # Make a connection to return the entity pb.
        connection = _Connection(entity_pb)
        client = self._makeOne(connection=connection)

        key = Key(KIND, ID, dataset_id=self.DATASET_ID)
        result, = client.get_multi([key])
        new_key = result.key

        # Check the returned value is as expected.
        self.assertFalse(new_key is key)
        self.assertEqual(new_key.dataset_id, self.DATASET_ID)
        self.assertEqual(new_key.path, PATH)
        self.assertEqual(list(result), ['foo'])
        self.assertEqual(result['foo'], 'Foo')

    def test_get_multi_hit_multiple_keys_same_dataset(self):
        from gcloud.datastore.key import Key
        from gcloud.datastore.test_connection import _Connection

        KIND = 'Kind'
        ID1 = 1234
        ID2 = 2345

        # Make a found entity pb to be returned from mock backend.
        entity_pb1 = _make_entity_pb(self.DATASET_ID, KIND, ID1)
        entity_pb2 = _make_entity_pb(self.DATASET_ID, KIND, ID2)

        # Make a connection to return the entity pbs.
        connection = _Connection(entity_pb1, entity_pb2)
        client = self._makeOne(connection=connection)

        key1 = Key(KIND, ID1, dataset_id=self.DATASET_ID)
        key2 = Key(KIND, ID2, dataset_id=self.DATASET_ID)
        retrieved1, retrieved2 = client.get_multi([key1, key2])

        # Check values match.
        self.assertEqual(retrieved1.key.path, key1.path)
        self.assertEqual(dict(retrieved1), {})
        self.assertEqual(retrieved2.key.path, key2.path)
        self.assertEqual(dict(retrieved2), {})

    def test_get_multi_hit_multiple_keys_different_dataset(self):
        from gcloud.datastore.key import Key

        DATASET_ID1 = 'DATASET'
        DATASET_ID2 = 'DATASET-ALT'

        # Make sure our IDs are actually different.
        self.assertNotEqual(DATASET_ID1, DATASET_ID2)

        key1 = Key('KIND', 1234, dataset_id=DATASET_ID1)
        key2 = Key('KIND', 1234, dataset_id=DATASET_ID2)
        client = self._makeOne(connection=object())

        with self.assertRaises(ValueError):
            client.get_multi([key1, key2])

    def test_get_multi_max_loops(self):
        from gcloud._testing import _Monkey
        from gcloud.datastore import client as _MUT
        from gcloud.datastore.key import Key
        from gcloud.datastore.test_connection import _Connection

        KIND = 'Kind'
        ID = 1234

        # Make a found entity pb to be returned from mock backend.
        entity_pb = _make_entity_pb(self.DATASET_ID, KIND, ID, 'foo', 'Foo')

        # Make a connection to return the entity pb.
        connection = _Connection(entity_pb)
        client = self._makeOne(connection=connection)

        key = Key(KIND, ID, dataset_id=self.DATASET_ID)
        deferred = []
        missing = []
        with _Monkey(_MUT, _MAX_LOOPS=-1):
            result = client.get_multi([key], missing=missing,
                                      deferred=deferred)

        # Make sure we have no results, even though the connection has been
        # set up as in `test_hit` to return a single result.
        self.assertEqual(result, [])
        self.assertEqual(missing, [])
        self.assertEqual(deferred, [])

    def test_put(self):
        _called_with = []

        def _put_multi(*args, **kw):
            _called_with.append((args, kw))

        client = self._makeOne()
        client.put_multi = _put_multi
        entity = object()

        client.put(entity)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['entities'], [entity])

    def test_put_multi_no_entities(self):
        client = self._makeOne(connection=object())
        self.assertEqual(client.put_multi([]), None)

    def test_put_multi_w_single_empty_entity(self):
        # https://github.com/GoogleCloudPlatform/gcloud-python/issues/649
        from gcloud.datastore.entity import Entity

        client = self._makeOne(connection=object())
        self.assertRaises(ValueError, client.put_multi, Entity())

    def test_put_multi_no_batch_w_partial_key(self):
        from gcloud.datastore.test_batch import _Connection
        from gcloud.datastore.test_batch import _Entity
        from gcloud.datastore.test_batch import _Key

        connection = _Connection()
        client = self._makeOne(connection=connection)
        entity = _Entity(foo=u'bar')
        key = entity.key = _Key(self.DATASET_ID)
        key._id = None

        result = client.put_multi([entity])
        self.assertTrue(result is None)

        self.assertEqual(len(connection._committed), 1)
        dataset_id, mutation, transaction_id = connection._committed[0]
        self.assertEqual(dataset_id, self.DATASET_ID)
        inserts = list(mutation.insert_auto_id)
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0].key, key.to_protobuf())
        properties = list(inserts[0].property)
        self.assertEqual(properties[0].name, 'foo')
        self.assertEqual(properties[0].value.string_value, u'bar')
        self.assertTrue(transaction_id is None)

    def test_put_multi_existing_batch_w_completed_key(self):
        from gcloud.datastore.test_batch import _Connection
        from gcloud.datastore.test_batch import _Entity
        from gcloud.datastore.test_batch import _Key

        connection = _Connection()
        client = self._makeOne(connection=connection)
        entity = _Entity(foo=u'bar')
        key = entity.key = _Key(self.DATASET_ID)

        with _NoCommitBatch(client) as CURR_BATCH:
            result = client.put_multi([entity])

        self.assertEqual(result, None)
        self.assertEqual(len(CURR_BATCH.mutation.insert_auto_id), 0)
        upserts = list(CURR_BATCH.mutation.upsert)
        self.assertEqual(len(upserts), 1)
        self.assertEqual(upserts[0].key, key.to_protobuf())
        properties = list(upserts[0].property)
        self.assertEqual(properties[0].name, 'foo')
        self.assertEqual(properties[0].value.string_value, u'bar')
        self.assertEqual(len(CURR_BATCH.mutation.delete), 0)

    def test_delete(self):
        _called_with = []

        def _delete_multi(*args, **kw):
            _called_with.append((args, kw))

        client = self._makeOne()
        client.delete_multi = _delete_multi
        key = object()

        client.delete(key)

        self.assertEqual(_called_with[0][0], ())
        self.assertEqual(_called_with[0][1]['keys'], [key])

    def test_delete_multi_no_keys(self):
        client = self._makeOne(connection=object())
        result = client.delete_multi([])
        self.assertEqual(result, None)

    def test_delete_multi_no_batch(self):
        from gcloud.datastore.test_batch import _Connection
        from gcloud.datastore.test_batch import _Key

        connection = _Connection()
        client = self._makeOne(connection=connection)
        key = _Key(self.DATASET_ID)

        result = client.delete_multi([key])
        self.assertEqual(result, None)
        self.assertEqual(len(connection._committed), 1)
        dataset_id, mutation, transaction_id = connection._committed[0]
        self.assertEqual(dataset_id, self.DATASET_ID)
        self.assertEqual(list(mutation.delete), [key.to_protobuf()])
        self.assertTrue(transaction_id is None)

    def test_delete_multi_w_existing_batch(self):
        from gcloud.datastore.test_batch import _Connection
        from gcloud.datastore.test_batch import _Key

        connection = _Connection()
        client = self._makeOne(connection=connection)
        key = _Key(self.DATASET_ID)

        with _NoCommitBatch(client) as CURR_BATCH:
            result = client.delete_multi([key])

        self.assertEqual(result, None)
        self.assertEqual(len(CURR_BATCH.mutation.insert_auto_id), 0)
        self.assertEqual(len(CURR_BATCH.mutation.upsert), 0)
        deletes = list(CURR_BATCH.mutation.delete)
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0], key._key)
        self.assertEqual(len(connection._committed), 0)

    def test_delete_multi_w_existing_transaction(self):
        from gcloud.datastore.test_batch import _Connection
        from gcloud.datastore.test_batch import _Key

        connection = _Connection()
        client = self._makeOne(connection=connection)
        key = _Key(self.DATASET_ID)

        with _NoCommitTransaction(client) as CURR_XACT:
            result = client.delete_multi([key])

        self.assertEqual(result, None)
        self.assertEqual(len(CURR_XACT.mutation.insert_auto_id), 0)
        self.assertEqual(len(CURR_XACT.mutation.upsert), 0)
        deletes = list(CURR_XACT.mutation.delete)
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0], key._key)
        self.assertEqual(len(connection._committed), 0)

    def test_allocate_ids_w_partial_key(self):
        from gcloud.datastore.test_batch import _Key
        from gcloud.datastore.test_connection import _Connection

        connection = _Connection()
        client = self._makeOne(connection=connection)
        NUM_IDS = 2

        INCOMPLETE_KEY = _Key(self.DATASET_ID)
        INCOMPLETE_KEY._id = None
        result = client.allocate_ids(INCOMPLETE_KEY, NUM_IDS)

        # Check the IDs returned.
        self.assertEqual([key._id for key in result], list(range(NUM_IDS)))

    def test_allocate_ids_with_completed_key(self):
        from gcloud.datastore.test_batch import _Key
        from gcloud.datastore.test_connection import _Connection

        connection = _Connection()
        client = self._makeOne(connection=connection)
        COMPLETE_KEY = _Key(self.DATASET_ID)
        self.assertRaises(ValueError, client.allocate_ids, COMPLETE_KEY, 2)

    def test_key_w_dataset_id(self):
        KIND = 'KIND'
        ID = 1234
        client = self._makeOne()
        self.assertRaises(TypeError,
                          client.key, KIND, ID, dataset_id=self.DATASET_ID)

    def test_key_wo_dataset_id(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        KIND = 'KIND'
        ID = 1234
        client = self._makeOne()

        with _Monkey(MUT, Key=_Dummy):
            key = client.key(KIND, ID)

        self.assertTrue(isinstance(key, _Dummy))
        self.assertEqual(key.args, (KIND, ID))
        expected_kwargs = {
            'dataset_id': self.DATASET_ID,
            'namespace': None,
        }
        self.assertEqual(key.kwargs, expected_kwargs)

    def test_key_w_namespace(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        KIND = 'KIND'
        ID = 1234
        NAMESPACE = object()
        client = self._makeOne(namespace=NAMESPACE)
        with _Monkey(MUT, Key=_Dummy):
            key = client.key(KIND, ID)

        self.assertTrue(isinstance(key, _Dummy))
        expected_kwargs = {
            'dataset_id': self.DATASET_ID,
            'namespace': NAMESPACE,
        }
        self.assertEqual(key.kwargs, expected_kwargs)

    def test_key_w_namespace_collision(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        KIND = 'KIND'
        ID = 1234
        NAMESPACE1 = object()
        NAMESPACE2 = object()
        client = self._makeOne(namespace=NAMESPACE1)
        with _Monkey(MUT, Key=_Dummy):
            key = client.key(KIND, ID, namespace=NAMESPACE2)

        self.assertTrue(isinstance(key, _Dummy))
        expected_kwargs = {
            'dataset_id': self.DATASET_ID,
            'namespace': NAMESPACE2,
        }
        self.assertEqual(key.kwargs, expected_kwargs)

    def test_batch(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        client = self._makeOne()

        with _Monkey(MUT, Batch=_Dummy):
            batch = client.batch()

        self.assertTrue(isinstance(batch, _Dummy))
        self.assertEqual(batch.args, (client,))
        self.assertEqual(batch.kwargs, {})

    def test_transaction(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        client = self._makeOne()

        with _Monkey(MUT, Transaction=_Dummy):
            xact = client.transaction()

        self.assertTrue(isinstance(xact, _Dummy))
        self.assertEqual(xact.args, (client,))
        self.assertEqual(xact.kwargs, {})

    def test_query_w_dataset_id(self):
        KIND = 'KIND'
        client = self._makeOne()
        self.assertRaises(TypeError,
                          client.query, kind=KIND, dataset_id=self.DATASET_ID)

    def test_query_w_defaults(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        client = self._makeOne()

        with _Monkey(MUT, Query=_Dummy):
            query = client.query()

        self.assertTrue(isinstance(query, _Dummy))
        self.assertEqual(query.args, ())
        expected_kwargs = {
            'dataset_id': self.DATASET_ID,
            'namespace': None,
        }
        self.assertEqual(query.kwargs, expected_kwargs)

    def test_query_explicit(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        KIND = 'KIND'
        NAMESPACE = 'NAMESPACE'
        ANCESTOR = object()
        FILTERS = [('PROPERTY', '==', 'VALUE')]
        PROJECTION = ['__key__']
        ORDER = ['PROPERTY']
        GROUP_BY = ['GROUPBY']
        client = self._makeOne()

        with _Monkey(MUT, Query=_Dummy):
            query = client.query(
                kind=KIND,
                namespace=NAMESPACE,
                ancestor=ANCESTOR,
                filters=FILTERS,
                projection=PROJECTION,
                order=ORDER,
                group_by=GROUP_BY,
                )

        self.assertTrue(isinstance(query, _Dummy))
        kwargs = {
            'dataset_id': self.DATASET_ID,
            'kind': KIND,
            'namespace': NAMESPACE,
            'ancestor': ANCESTOR,
            'filters': FILTERS,
            'projection': PROJECTION,
            'order': ORDER,
            'group_by': GROUP_BY,
        }
        self.assertEqual(query.args, ())
        self.assertEqual(query.kwargs, kwargs)

    def test_query_w_namespace(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        KIND = 'KIND'
        NAMESPACE = object()
        client = self._makeOne(namespace=NAMESPACE)
        with _Monkey(MUT, Query=_Dummy):
            query = client.query(kind=KIND)

        self.assertTrue(isinstance(query, _Dummy))
        self.assertEqual(query.args, ())
        expected_kwargs = {
            'dataset_id': self.DATASET_ID,
            'namespace': NAMESPACE,
            'kind': KIND,
        }
        self.assertEqual(query.kwargs, expected_kwargs)

    def test_query_w_namespace_collision(self):
        from gcloud.datastore import client as MUT
        from gcloud._testing import _Monkey

        KIND = 'KIND'
        NAMESPACE1 = object()
        NAMESPACE2 = object()
        client = self._makeOne(namespace=NAMESPACE1)
        with _Monkey(MUT, Query=_Dummy):
            query = client.query(kind=KIND, namespace=NAMESPACE2)

        self.assertTrue(isinstance(query, _Dummy))
        self.assertEqual(query.args, ())
        expected_kwargs = {
            'dataset_id': self.DATASET_ID,
            'namespace': NAMESPACE2,
            'kind': KIND,
        }
        self.assertEqual(query.kwargs, expected_kwargs)


class _Dummy(object):

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _HttpMultiple(object):

    def __init__(self, *responses):
        self._called_with = []
        self._responses = list(responses)

    def request(self, **kw):
        self._called_with.append(kw)
        result, self._responses = self._responses[0], self._responses[1:]
        return result


class _NoCommitBatch(object):

    def __init__(self, client):
        from gcloud.datastore.batch import Batch
        self._client = client
        self._batch = Batch(client)

    def __enter__(self):
        self._client._push_batch(self._batch)
        return self._batch

    def __exit__(self, *args):
        self._client._pop_batch()


class _NoCommitTransaction(object):

    def __init__(self, client, transaction_id='TRANSACTION'):
        from gcloud.datastore.transaction import Transaction
        self._client = client
        xact = self._transaction = Transaction(client)
        xact._id = transaction_id

    def __enter__(self):
        self._client._push_batch(self._transaction)
        return self._transaction

    def __exit__(self, *args):
        self._client._pop_batch()
