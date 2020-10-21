#
# Copyright 2019 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the permission viewset."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import tenant_context

from api.models import User
from management.models import Permission
from tests.identity_request import IdentityRequest

OPTION_URL = reverse("permission-options")
LIST_URL = reverse("permission-list")
CLIENT = APIClient()


class PermissionViewsetTests(IdentityRequest):
    """Test the permission viewset."""

    def setUp(self):
        """Set up the permission viewset tests."""
        super().setUp()
        request = self.request_context["request"]
        user = User()
        user.username = self.user_data["username"]
        user.account = self.customer_data["account_id"]
        request.user = user

        self.display_fields = {"application", "resource_type", "verb", "permission"}

        with tenant_context(self.tenant):
            self.permissionA = Permission.objects.create(permission="rbac:roles:read")
            self.permissionB = Permission.objects.create(permission="rbac:*:*")
            self.permissionC = Permission.objects.create(permission="acme:*:*")
            self.permissionD = Permission.objects.create(permission="acme:*:write")
            self.permissionE = Permission.objects.create(permission="*:*:*")
            self.permissionF = Permission.objects.create(permission="*:bar:*")
            self.permissionG = Permission.objects.create(permission="*:*:baz")
            self.permissionH = Permission.objects.create(permission="*:bar:baz")
            self.permissionI = Permission.objects.create(permission="foo:bar:*", description="Description test.")

    def tearDown(self):
        """Tear down permission viewset tests."""
        with tenant_context(self.tenant):
            Permission.objects.all().delete()

    def test_read_permission_list_success(self):
        """Test that we can read a list of permissions."""
        response = CLIENT.get(LIST_URL, **self.headers)

        # three parts in response: meta, links and data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for keyname in ["meta", "links", "data"]:
            self.assertIn(keyname, response.data)
        self.assertIsInstance(response.data.get("data"), list)
        self.assertEqual(len(response.data.get("data")), 9)

        for perm in response.data.get("data"):
            self.assertIsNotNone(perm.get("application"))
            self.assertIsNotNone(perm.get("resource_type"))
            self.assertIsNotNone(perm.get("verb"))
            self.assertIsNotNone(perm.get("permission"))
            if perm["permission"] == "foo:bar:*":
                self.assertEqual(perm["description"], "Description test.")
            else:
                self.assertEqual(self.display_fields, set(perm.keys()))

    def test_read_permission_list_application_filter(self):
        """Test that we can filter a list of permissions by application."""
        url = LIST_URL
        url = f"{url}?application=rbac"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 2)

    def test_read_permission_list_resource_type_filter(self):
        """Test that we can filter a list of permissions by resource_type."""
        url = LIST_URL
        url = f"{url}?resource_type=roles"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 1)
        self.assertEqual(response.data.get("data")[0].get("permission"), self.permissionA.permission)

    def test_read_permission_list_verb_filter(self):
        """Test that we can filter a list of permissions by verb."""
        url = LIST_URL
        url = f"{url}?verb=read"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 1)
        self.assertEqual(response.data.get("data")[0].get("permission"), self.permissionA.permission)

    def test_read_permission_list_permission_filter(self):
        """Test that we can filter a list of permissions by permission."""
        url = LIST_URL
        url = f"{url}?permission=rbac:*:*"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 1)
        self.assertEqual(response.data.get("data")[0].get("permission"), self.permissionB.permission)

    def test_get_list_is_the_only_valid_method(self):
        """Test GET on /permissions/ is the only valid method."""
        response = CLIENT.post(LIST_URL, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = CLIENT.put(LIST_URL, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        response = CLIENT.delete(LIST_URL, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_filters_multiple_application_values(self):
        """Test that we can filter permissions with multiple application values."""
        with tenant_context(self.tenant):
            expected_permissions = list(
                Permission.objects.filter(application__in=["rbac", "acme"]).values_list("permission", flat=True)
            )

        url = LIST_URL
        url = f"{url}?application=rbac,acme"
        response = CLIENT.get(url, **self.headers)
        response_permissions = [p.get("permission") for p in response.data.get("data")]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 4)
        self.assertCountEqual(expected_permissions, response_permissions)

    def test_filters_multiple_resource_type_values(self):
        """Test that we can filter permissions with multiple resource_type values."""
        with tenant_context(self.tenant):
            expected_permissions = list(
                Permission.objects.filter(resource_type__in=["roles", "*"]).values_list("permission", flat=True)
            )

        url = LIST_URL
        url = f"{url}?resource_type=roles,*"
        response = CLIENT.get(url, **self.headers)
        response_permissions = [p.get("permission") for p in response.data.get("data")]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 6)
        self.assertCountEqual(expected_permissions, response_permissions)

    def test_filters_multiple_verb_values(self):
        """Test that we can filter permissions with multiple verb values."""
        with tenant_context(self.tenant):
            expected_permissions = list(
                Permission.objects.values_list("permission", flat=True).filter(verb__in=["read", "write"])
            )

        url = LIST_URL
        url = f"{url}?verb=read,write"
        response = CLIENT.get(url, **self.headers)
        response_permissions = [p.get("permission") for p in response.data.get("data")]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 2)
        self.assertCountEqual(expected_permissions, response_permissions)

    def test_query_invalid_field_fail(self):
        """Test that query invalid field fail."""

        url = f"{OPTION_URL}?field=invalid"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_query_without_field_fail(self):
        """Test that query invalid field fail."""

        url = f"{OPTION_URL}"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_fields_with_limit(self):
        """Test that we can obtain the expected field with pagination."""
        url = f"{OPTION_URL}?field=application&limit=1"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertIsInstance(response.data.get("data"), list)
        self.assertEqual(len(response.data.get("data")), 1)
        self.assertEqual(response.data.get("meta").get("count"), 4)
        self.assertEqual(response.data.get("meta").get("limit"), 1)

    def test_get_fields_without_limit(self):
        """Test that we can obtain the expected field without pagination."""

        url = f"{OPTION_URL}?field=application"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("data"))
        self.assertIsInstance(response.data.get("data"), list)
        self.assertEqual(response.data.get("meta").get("limit"), 1000)

    def test_return_options_of_application(self):
        """Test that we can return options of application."""
        with tenant_context(self.tenant):
            expected_all = Permission.objects.values_list("application", flat=True).distinct()
            expected_filtered = (
                Permission.objects.filter(verb__in=["read", "write"]).values_list("application", flat=True).distinct()
            )

        url_all = f"{OPTION_URL}?field=application"
        url_filtered = f"{OPTION_URL}?field=application&verb=read,write"
        response_all = CLIENT.get(url_all, **self.headers)
        response_filtered = CLIENT.get(url_filtered, **self.headers)

        self.assertEqual(response_all.status_code, status.HTTP_200_OK)
        self.assertEqual(response_filtered.status_code, status.HTTP_200_OK)
        self.assertCountEqual(expected_all, response_all.data.get("data"))
        self.assertCountEqual(expected_filtered, response_filtered.data.get("data"))

    def test_return_options_of_resource_type(self):
        """Test that we can return options of resource_type."""
        with tenant_context(self.tenant):
            expected_all = Permission.objects.values_list("resource_type", flat=True).distinct()
            expected_filtered = (
                Permission.objects.filter(application="acme").values_list("resource_type", flat=True).distinct()
            )

        url_all = f"{OPTION_URL}?field=resource_type"
        url_filtered = f"{OPTION_URL}?field=resource_type&application=acme"
        response_all = CLIENT.get(url_all, **self.headers)
        response_filtered = CLIENT.get(url_filtered, **self.headers)

        self.assertEqual(response_all.status_code, status.HTTP_200_OK)
        self.assertEqual(response_filtered.status_code, status.HTTP_200_OK)
        self.assertCountEqual(expected_all, response_all.data.get("data"))
        self.assertCountEqual(expected_filtered, response_filtered.data.get("data"))

    def test_return_options_of_verb(self):
        """Test that we can return options of verb."""
        with tenant_context(self.tenant):
            expected_all = Permission.objects.values_list("verb", flat=True).distinct()
            expected_filtered = (
                Permission.objects.filter(resource_type="roles").values_list("verb", flat=True).distinct()
            )

        url_all = f"{OPTION_URL}?field=verb"
        url_filtered = f"{OPTION_URL}?field=verb&resource_type=roles"
        response_all = CLIENT.get(url_all, **self.headers)
        response_filtered = CLIENT.get(url_filtered, **self.headers)

        self.assertEqual(response_all.status_code, status.HTTP_200_OK)
        self.assertEqual(response_filtered.status_code, status.HTTP_200_OK)
        self.assertCountEqual(expected_all, response_all.data.get("data"))
        self.assertCountEqual(expected_filtered, response_filtered.data.get("data"))

    def test_return_options_with_comma_separated_filter(self):
        """Test that we can return options with comma separated filter."""
        with tenant_context(self.tenant):
            expected = (
                Permission.objects.filter(resource_type__in=["roles", "*"]).values_list("verb", flat=True).distinct()
            )

        url = f"{OPTION_URL}?field=verb&resource_type=roles,*"
        response = CLIENT.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertCountEqual(expected, response.data.get("data"))

    def test_exclude_globals_filters_any_globals_out_when_true(self):
        """Test that we filter out any global permissions when exclude_globals=true."""
        with tenant_context(self.tenant):
            expected = list(
                Permission.objects.filter(permission=self.permissionA.permission).values_list("permission", flat=True)
            )

        response = CLIENT.get(f"{LIST_URL}?exclude_globals=true", **self.headers)
        response_permissions = [p.get("permission") for p in response.data.get("data")]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 1)
        self.assertCountEqual(expected, response_permissions)

    def test_exclude_globals_filters_no_globals_out_when_false(self):
        """Test that we do not filter out any global permissions when exclude_globals=false."""
        with tenant_context(self.tenant):
            expected = list(Permission.objects.values_list("permission", flat=True))

        response = CLIENT.get(f"{LIST_URL}?exclude_globals=false", **self.headers)
        response_permissions = [p.get("permission") for p in response.data.get("data")]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 9)
        self.assertCountEqual(expected, response_permissions)

    def test_exclude_globals_filters_no_globals_out_by_default(self):
        """Test that we do not filter out any global permissions when exclude_globals is unset."""
        with tenant_context(self.tenant):
            expected = list(Permission.objects.values_list("permission", flat=True))

        response = CLIENT.get(LIST_URL, **self.headers)
        response_permissions = [p.get("permission") for p in response.data.get("data")]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data.get("data")), 9)
        self.assertCountEqual(expected, response_permissions)

    def test_exclude_globals_fails_with_invalid_value(self):
        """Test that we return a 400 when exclude_globals is not a supported value."""
        response = CLIENT.get(f"{LIST_URL}?exclude_globals=foo", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PermissionViewsetTestsNonAdmin(IdentityRequest):
    """Test the permission viewset."""

    def setUp(self):
        """Set up the permission viewset tests."""
        super().setUp()

        self.user_data = self._create_user_data()
        self.customer = self._create_customer_data()
        self.request_context = self._create_request_context(self.customer, self.user_data, is_org_admin=False)

        request = self.request_context["request"]
        self.headers = request.META

        with tenant_context(self.tenant):
            self.permission = Permission.objects.create(permission="rbac:roles:read")
            self.permission.save()

    def tearDown(self):
        """Tear down permission viewset tests."""
        with tenant_context(self.tenant):
            Permission.objects.all().delete()

    def test_read_permission_list_fail(self):
        """Test that we can not read a list of permissions as a non-admin."""
        response = CLIENT.get(LIST_URL, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_read_permission_options_list_fail(self):
        """Test that we can not read a list of filed options of permissions  as a non-admin."""
        url = f"{OPTION_URL}?field=application"
        response = CLIENT.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
