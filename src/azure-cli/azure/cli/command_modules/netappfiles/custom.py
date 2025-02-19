# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# pylint: disable=line-too-long

from knack.log import get_logger
from azure.mgmt.netapp.models import ActiveDirectory, NetAppAccount, NetAppAccountPatch, CapacityPool, CapacityPoolPatch, Volume, VolumePatch, VolumePropertiesExportPolicy, ExportPolicyRule, Snapshot
from azure.cli.core.commands.client_factory import get_subscription_id

logger = get_logger(__name__)

# RP expted bytes but CLI allows integer TiBs for ease of use
gib_scale = 1024 * 1024 * 1024
tib_scale = gib_scale * 1024


def _update_mapper(existing, new, keys):
    for key in keys:
        existing_value = getattr(existing, key)
        new_value = getattr(new, key)
        setattr(new, key, new_value if new_value is not None else existing_value)


# pylint: disable=unused-argument
# account update - active_directory is amended with subgroup commands
def create_account(cmd, client, account_name, resource_group_name, location, tags=None):
    body = NetAppAccount(location=location, tags=tags)
    return client.create_or_update(body, resource_group_name, account_name)


# pylint: disable=unused-argument
# add an active directory to the netapp account
# current limitation is 1 AD/subscription
def add_active_directory(cmd, instance, account_name, resource_group_name, username, password, domain, dns, smb_server_name, organizational_unit=None):
    active_directories = []
    active_directory = ActiveDirectory(username=username, password=password, domain=domain, dns=dns, smb_server_name=smb_server_name, organizational_unit=organizational_unit)
    active_directories.append(active_directory)
    body = NetAppAccountPatch(active_directories=active_directories)
    _update_mapper(instance, body, ['active_directories'])
    return body


# list all active directories
def list_active_directories(cmd, client, account_name, resource_group_name):
    return client.get(resource_group_name, account_name).active_directories


# removes the active directory entry matching the provided id
# Note:
# The RP implementation is such that patch of active directories provides an addition type amendment, i.e.
# absence of an AD does not remove the ADs already present. To perform this a put request is required that
# asserts exactly the content provided, replacing whatever is already present including removing it if none
# are present
def remove_active_directory(cmd, client, account_name, resource_group_name, active_directory):
    instance = client.get(resource_group_name, account_name)

    for ad in instance.active_directories:
        if ad.active_directory_id == active_directory:
            instance.active_directories.remove(ad)

    active_directories = instance.active_directories
    body = NetAppAccount(location=instance.location, tags=instance.tags, active_directories=active_directories)

    return client.create_or_update(body, resource_group_name, account_name)


# account update, active_directory is amended with subgroup commands
def patch_account(cmd, instance, account_name, resource_group_name, tags=None):
    body = NetAppAccountPatch(tags=tags)
    _update_mapper(instance, body, ['tags'])
    return body


def create_pool(cmd, client, account_name, pool_name, resource_group_name, service_level, location, size, tags=None):
    body = CapacityPool(service_level=service_level, size=int(size) * tib_scale, location=location, tags=tags)
    return client.create_or_update(body, resource_group_name, account_name, pool_name)


# pool update
def patch_pool(cmd, instance, size=None, service_level=None, tags=None):
    # put operation to update the record
    if size is not None:
        size = int(size) * tib_scale
    body = CapacityPoolPatch(service_level=service_level, size=size, tags=tags)
    _update_mapper(instance, body, ['service_level', 'size', 'tags'])
    return body


def create_volume(cmd, client, account_name, pool_name, volume_name, resource_group_name, location, creation_token, usage_threshold, vnet, subnet='default', service_level=None, protocol_types=None, tags=None):
    subs_id = get_subscription_id(cmd.cli_ctx)
    subnet_id = "/subscriptions/%s/resourceGroups/%s/providers/Microsoft.Network/virtualNetworks/%s/subnets/%s" % (subs_id, resource_group_name, vnet, subnet)
    body = Volume(
        usage_threshold=int(usage_threshold) * gib_scale,
        creation_token=creation_token,
        service_level=service_level,
        location=location,
        subnet_id=subnet_id,
        protocol_types=protocol_types,
        tags=tags)

    return client.create_or_update(body, resource_group_name, account_name, pool_name, volume_name)


# volume update
def patch_volume(cmd, instance, usage_threshold=None, service_level=None, protocol_types=None, tags=None):
    params = VolumePatch(
        usage_threshold=None if usage_threshold is None else int(usage_threshold) * gib_scale,
        service_level=service_level,
        protocol_types=protocol_types,
        tags=tags)
    _update_mapper(instance, params, ['service_level', 'usage_threshold', 'tags'])
    return params


# add new rule to policy
def add_export_policy_rule(cmd, instance, allowed_clients, rule_index, unix_read_only, unix_read_write, cifs, nfsv3, nfsv4):
    rules = []

    export_policy = ExportPolicyRule(rule_index=rule_index, unix_read_only=unix_read_only, unix_read_write=unix_read_write, cifs=cifs, nfsv3=nfsv3, nfsv4=nfsv4, allowed_clients=allowed_clients)

    rules.append(export_policy)
    for rule in instance.export_policy.rules:
        rules.append(rule)

    volume_export_policy = VolumePropertiesExportPolicy(rules=rules)

    params = VolumePatch(
        export_policy=volume_export_policy)
    _update_mapper(instance, params, ['export_policy'])
    return params


# list all rules
def list_export_policy_rules(cmd, client, account_name, pool_name, volume_name, resource_group_name):
    return client.get(resource_group_name, account_name, pool_name, volume_name).export_policy


# delete rule by specific index
def remove_export_policy_rule(cmd, instance, rule_index):
    # look for the rule and remove
    for rule in instance.export_policy.rules:
        if rule.rule_index == int(rule_index):
            instance.export_policy.rules.remove(rule)

    return instance


def create_snapshot(cmd, client, account_name, pool_name, volume_name, snapshot_name, resource_group_name, location, file_system_id=None):
    body = Snapshot(location=location, file_system_id=file_system_id)
    return client.create(body, resource_group_name, account_name, pool_name, volume_name, snapshot_name)
