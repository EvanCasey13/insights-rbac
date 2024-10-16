"""
Copyright 2019 Red Hat, Inc.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import logging
from typing import Iterable

from django.conf import settings
from kessel.relations.v1beta1 import common_pb2
from management.models import Workspace
from management.role.model import BindingMapping, Role
from migration_tool.models import V2rolebinding
from migration_tool.sharedSystemRolesReplicatedRoleBindings import v1_role_to_v2_bindings
from migration_tool.utils import create_relationship, output_relationships

from api.models import Tenant


logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


def get_kessel_relation_tuples(
    v2_role_bindings: Iterable[V2rolebinding],
    default_workspace: Workspace,
) -> list[common_pb2.Relationship]:
    """Generate a set of relationships and BindingMappings for the given set of v2 role bindings."""
    relationships: list[common_pb2.Relationship] = list()

    for v2_role_binding in v2_role_bindings:
        relationships.extend(v2_role_binding.as_tuples())

        bound_resource = v2_role_binding.resource

        # Is this a workspace binding, but not to the root workspace?
        # If so, ensure this workspace is a child of the root workspace.
        # All other resource-resource or resource-workspace relations
        # which may be implied or necessary are intentionally ignored.
        # These should come from the apps that own the resource.
        if bound_resource.resource_type == ("rbac", "workspace") and not bound_resource.resource_id == str(
            default_workspace.uuid
        ):
            # This is not strictly necessary here and the relation may be a duplicate.
            # Once we have more Workspace API / Inventory Group migration progress,
            # this block can and probably should be removed.
            # One of those APIs will add it themselves.
            relationships.append(
                create_relationship(
                    bound_resource.resource_type,
                    bound_resource.resource_id,
                    ("rbac", "workspace"),
                    str(default_workspace.uuid),
                    "parent",
                )
            )

    return relationships


def migrate_role(
    role: Role,
    write_relationships: bool,
    default_workspace: Workspace,
    current_bindings: Iterable[BindingMapping] = [],
) -> tuple[list[common_pb2.Relationship], list[BindingMapping]]:
    """
    Migrate a role from v1 to v2, returning the tuples and mappings.

    The mappings are returned so that we can reconstitute the corresponding tuples for a given role.
    This is needed so we can remove those tuples when the role changes if needed.
    """
    v2_role_bindings = v1_role_to_v2_bindings(role, default_workspace, current_bindings)
    relationships = get_kessel_relation_tuples([m.get_role_binding() for m in v2_role_bindings], default_workspace)
    output_relationships(relationships, write_relationships)
    return relationships, v2_role_bindings


def migrate_workspace(tenant: Tenant, write_relationships: bool):
    """Migrate a workspace from v1 to v2."""
    root_workspace, _ = Workspace.objects.get_or_create(
        tenant=tenant,
        type=Workspace.Types.ROOT,
        name="Root Workspace",
    )
    default_workspace, _ = Workspace.objects.get_or_create(
        tenant=tenant,
        type=Workspace.Types.DEFAULT,
        parent=root_workspace,
        name="Default Workspace",
    )

    relationships = [
        create_relationship(
            ("rbac", "workspace"),
            str(default_workspace.uuid),
            ("rbac", "workspace"),
            str(root_workspace.uuid),
            "parent",
        ),
        create_relationship(
            ("rbac", "workspace"), str(root_workspace.uuid), ("rbac", "tenant"), tenant.org_id, "parent"
        ),
    ]
    # Include platform for tenant
    relationships.append(
        create_relationship(
            ("rbac", "tenant"), str(tenant.org_id), ("rbac", "platform"), settings.ENV_NAME, "platform"
        )
    )
    output_relationships(relationships, write_relationships)
    return root_workspace, default_workspace


def migrate_users(tenant: Tenant, write_relationships: bool):
    """Write users relationship to tenant."""
    relationships = [
        create_relationship(
            ("rbac", "tenant"), str(tenant.org_id), ("rbac", "principal"), str(principal.uuid), "member"
        )
        for principal in tenant.principal_set.all()
    ]
    output_relationships(relationships, write_relationships)


def migrate_users_for_groups(tenant: Tenant, write_relationships: bool):
    """Write users relationship to groups."""
    relationships = []
    for group in tenant.group_set.exclude(platform_default=True):
        user_set = group.principals.all()
        for user in user_set:
            relationships.append(
                create_relationship(
                    ("rbac", "group"), str(group.uuid), ("rbac", "principal"), str(user.uuid), "member"
                )
            )
    # Explicitly create relationships for platform default group
    group_default = tenant.group_set.filter(platform_default=True).first()
    if not group_default:  # Means it is not custom platform_default
        group_default = Tenant.objects.get(tenant_name="public").group_set.get(platform_default=True)
    user_set = tenant.principal_set.filter(cross_account=False)
    for user in user_set:
        relationships.append(
            create_relationship(
                ("rbac", "group"), str(group_default.uuid), ("rbac", "principal"), str(user.uuid), "member"
            )
        )
    output_relationships(relationships, write_relationships)


def migrate_data_for_tenant(tenant: Tenant, exclude_apps: list, write_relationships: bool):
    """Migrate all data for a given tenant."""
    logger.info("Creating workspace.")
    _, default_workspace = migrate_workspace(tenant, write_relationships)
    logger.info("Workspace migrated.")

    logger.info("Relating users to tenant.")
    migrate_users(tenant, write_relationships)
    logger.info("Finished relationship between users and tenant.")

    logger.info("Migrating relations of group and user.")
    migrate_users_for_groups(tenant, write_relationships)
    logger.info("Finished migrating relations of group and user.")

    roles = tenant.role_set.all()
    if exclude_apps:
        roles = roles.exclude(access__permission__application__in=exclude_apps)

    for role in roles:
        logger.info(f"Migrating role: {role.name} with UUID {role.uuid}.")

        _, mappings = migrate_role(role, write_relationships, default_workspace)

        # Conflits are not ignored in order to prevent this from
        # accidentally running concurrently with dual-writes.
        # If migration should be rerun, then the bindings table should be dropped.
        # If changing this to allow updates,
        # always ensure writes are paused before running.
        # This must always be the case, but this should at least start failing you if you forget.
        BindingMapping.objects.bulk_create(mappings, ignore_conflicts=False)

        logger.info(f"Migration completed for role: {role.name} with UUID {role.uuid}.")
    logger.info(f"Migrated {roles.count()} roles for tenant: {tenant.org_id}")


def migrate_data(exclude_apps: list = [], orgs: list = [], write_relationships: bool = False):
    """Migrate all data for all tenants."""
    count = 0
    tenants = Tenant.objects.exclude(tenant_name="public")
    if orgs:
        tenants = tenants.filter(org_id__in=orgs)
    total = tenants.count()
    for tenant in tenants.iterator():
        logger.info(f"Migrating data for tenant: {tenant.org_id}")
        try:
            migrate_data_for_tenant(tenant, exclude_apps, write_relationships)
        except Exception as e:
            logger.error(f"Failed to migrate data for tenant: {tenant.org_id}. Error: {e}")
            raise e
        count += 1
        logger.info(f"Finished migrating data for tenant: {tenant.org_id}. {count} of {total} tenants completed")
    logger.info("Finished migrating data for all tenants")
