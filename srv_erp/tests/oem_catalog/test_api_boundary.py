"""Boundary regressions runnable without Frappe or a database."""
import importlib
from types import ModuleType, SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, call, patch

from srv_erp.oem_catalog.domain.models import CatalogError


class TestAPIBoundary(unittest.TestCase):
    def setUp(self):
        frappe = ModuleType('frappe')
        frappe.session = SimpleNamespace(user='operator@example.com')
        frappe.db = Mock()
        frappe._ = lambda message: message
        frappe.PermissionError = type('PermissionError', (Exception,), {})
        frappe.QueryDeadlockError = type('Deadlock', (Exception,), {})
        frappe.QueryTimeoutError = type('Timeout', (Exception,), {})
        def throw(message, exception=ValueError):
            raise exception(message)
        frappe.throw = throw
        def whitelist(methods):
            def decorate(fn):
                fn.allowed_methods = methods
                return fn
            return decorate
        frappe.whitelist = whitelist
        utils = ModuleType('frappe.utils')
        utils.getdate = Mock()
        utils.today = Mock()
        self.modules = patch.dict(sys.modules, {'frappe': frappe, 'frappe.utils': utils})
        self.modules.start()
        # Reload only these modules under the temporary framework stub.
        for name in ('srv_erp.oem_catalog.api', 'srv_erp.oem_catalog.infrastructure.api_boundary',
                     'srv_erp.oem_catalog.infrastructure.dto', 'srv_erp.oem_catalog.permissions',
                     'srv_erp.oem_catalog.application.request_queries',
                     'srv_erp.oem_catalog.application.catalogue_queries'):
            sys.modules.pop(name, None)
        self.boundary = importlib.import_module('srv_erp.oem_catalog.infrastructure.api_boundary')
        self.frappe = frappe
        self.addCleanup(self.modules.stop)

    def test_guest_cannot_execute_handler_or_open_savepoint(self):
        self.frappe.session.user = 'Guest'
        handler = Mock()
        with self.assertRaises(self.frappe.PermissionError):
            self.boundary.endpoint(write=True)(handler)()
        handler.assert_not_called()
        self.frappe.db.savepoint.assert_not_called()

    def test_verbs_metadata_and_response_version(self):
        def handler(value=1):
            """Example docstring."""
            return {'value': value}
        read = self.boundary.endpoint()(handler)
        write = self.boundary.endpoint(write=True)(handler)
        self.assertEqual(read.allowed_methods, ['GET', 'POST'])
        self.assertEqual(write.allowed_methods, ['POST'])
        self.assertEqual(read.__name__, handler.__name__)
        self.assertEqual(read.__doc__, handler.__doc__)
        self.assertEqual(read(2), {'value': 2, 'api_version': 1})
        self.assertEqual(self.boundary.endpoint()(lambda: {'api_version': 2})(), {'api_version': 2})
        self.assertEqual(self.boundary.endpoint()(lambda: [1])(), [1])
        self.frappe.db.savepoint.assert_not_called()
        write()
        self.frappe.db.savepoint.assert_called_once_with('oem_command_boundary')

    def test_domain_and_unexpected_errors_roll_back_only_command_savepoint(self):
        for error in (CatalogError('INVALID_INPUT', 'bad choice'), RuntimeError('controller failed')):
            with self.subTest(error=error):
                self.frappe.db.reset_mock()
                handler = Mock(side_effect=error)
                with self.assertRaisesRegex((ValueError, RuntimeError), str(error)):
                    self.boundary.endpoint(write=True)(handler)()
                self.frappe.db.rollback.assert_called_once_with(save_point='oem_command_boundary')
                self.assertEqual(handler.call_count, 1)
        with self.assertRaisesRegex(ValueError, 'INVALID_INPUT: bad choice'):
            self.boundary.endpoint()(Mock(side_effect=CatalogError('INVALID_INPUT', 'bad choice')))()

    def test_write_retries_deadlock_and_timeout_then_returns_result(self):
        handler = Mock(side_effect=[self.frappe.QueryDeadlockError(), self.frappe.QueryTimeoutError(), {'ok': True}])
        with patch.object(self.boundary.time, 'sleep') as sleep:
            result = self.boundary.endpoint(write=True)(handler)()
        self.assertEqual(result, {'ok': True, 'api_version': 1})
        self.assertEqual(self.frappe.db.rollback.call_args_list, [call(), call()])
        self.assertEqual(self.frappe.db.savepoint.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(.05), call(.1)])

    def test_retry_exhaustion_and_read_failure_preserve_exception(self):
        error = self.frappe.QueryDeadlockError('deadlock')
        for write, attempts in ((True, 3), (False, 1)):
            with self.subTest(write=write):
                self.frappe.db.reset_mock()
                handler = Mock(side_effect=error)
                with patch.object(self.boundary.time, 'sleep'), self.assertRaises(self.frappe.QueryDeadlockError) as raised:
                    self.boundary.endpoint(write=write)(handler)()
                self.assertIs(raised.exception, error)
                self.assertEqual(handler.call_count, attempts)
                self.assertEqual(self.frappe.db.rollback.call_args_list, [call()] * attempts)

    def test_composed_requests_use_query_service_and_keep_actor_filter(self):
        queries = importlib.import_module('srv_erp.oem_catalog.application.request_queries')
        self.frappe.get_all = Mock(return_value=[SimpleNamespace(request='REQ-1'), SimpleNamespace(request='REQ-2')])
        with patch.object(queries, 'require_role') as authorize, patch.object(queries, 'get_request_status', side_effect=[{'request': 'REQ-1'}, {'request': 'REQ-2'}]) as status:
            result = queries.get_my_requests(-10)
        authorize.assert_called_once_with()
        self.assertEqual(status.call_args_list, [call('REQ-1'), call('REQ-2')])
        self.assertEqual(result['requests'], [{'request': 'REQ-1'}, {'request': 'REQ-2'}])
        self.assertEqual(self.frappe.get_all.call_args.kwargs['filters'], {'actor': self.frappe.session.user})
        self.assertEqual(self.frappe.get_all.call_args.kwargs['start'], 0)
        self.frappe.db.savepoint.assert_not_called()

    def test_request_access_is_checked_before_sources_are_read(self):
        queries = importlib.import_module('srv_erp.oem_catalog.application.request_queries')
        self.frappe.get_doc = Mock(return_value=SimpleNamespace(name='REQ-1'))
        self.frappe.get_all = Mock()
        with patch.object(queries, 'request_access', side_effect=self.frappe.PermissionError('denied')):
            with self.assertRaises(self.frappe.PermissionError):
                queries.get_request_status('REQ-1')
        self.frappe.get_all.assert_not_called()

    def test_public_search_forwards_query_value_without_shadowing(self):
        api = importlib.import_module('srv_erp.oem_catalog.api')
        queries = importlib.import_module('srv_erp.oem_catalog.application.catalogue_queries')
        with patch.object(queries, 'search_products', return_value={'products': []}) as search:
            result = api.search_products({'company': 'Example'}, query='enclosure', cursor=30, limit=5)
        search.assert_called_once_with({'company': 'Example'}, 'enclosure', 30, 5)
        self.assertEqual(result, {'products': [], 'api_version': 1})

    def test_catalogue_search_preserves_pilot_scope_and_permission_aware_list(self):
        queries = importlib.import_module('srv_erp.oem_catalog.application.catalogue_queries')
        self.frappe.get_list = Mock(return_value=[{'name': 'PRODUCT'}])
        scope = SimpleNamespace(mode='Pilot', pilot_scope=[SimpleNamespace(kind='Product', reference='PRODUCT')])
        with patch.object(queries, 'authorize_context', return_value=scope) as authorize:
            result = queries.search_products({'company': 'Example'}, 'label', cursor=5, limit=1)
        authorize.assert_called_once_with({'company': 'Example'})
        options = self.frappe.get_list.call_args.kwargs
        self.assertEqual(options['filters'], {'lifecycle': 'Active', 'name': ['in', ['PRODUCT']]})
        self.assertEqual(options['start'], 5)
        self.assertEqual(options['page_length'], 1)
        self.assertEqual(options['order_by'], 'catalogue_code asc')
        self.assertEqual(result, {'products': [{'name': 'PRODUCT'}], 'next_cursor': 6})
        for cursor, limit, query in ((-1, 1, ''), (0, 0, ''), (0, 1, 'x' * 101)):
            with patch.object(queries, 'authorize_context', return_value=scope), self.assertRaises(ValueError):
                queries.search_products({}, query, cursor, limit)
