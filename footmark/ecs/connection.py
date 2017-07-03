# encoding: utf-8
"""
Represents a connection to the ECS service.
"""

import warnings

import six
import time
import json
import logging
from footmark.connection import ACSQueryConnection
from footmark.ecs.instance import Instance
from footmark.ecs.regioninfo import RegionInfo
from footmark.ecs.securitygroup import SecurityGroup
from footmark.ecs.volume import Disk
from footmark.exception import ECSResponseError, FootmarkServerError
from functools import wraps
from footmark.resultset import ResultSet
# from aliyunsdkecs.request.v20140526.DescribeSecurityGroupAttributeRequest import
from aliyunsdkcore.acs_exception.exceptions import ServerException


class ECSConnection(ACSQueryConnection):
    SDKVersion = '2014-05-26'
    DefaultRegionId = 'cn-hangzhou'
    DefaultRegionName = u'杭州'.encode("UTF-8")
    ResponseError = ECSResponseError

    def __init__(self, acs_access_key_id=None, acs_secret_access_key=None,
                 region=None, sdk_version=None, security_token=None, user_agent=None):
        """
        Init method to create a new connection to ECS.
        """
        if not region:
            region = RegionInfo(self, self.DefaultRegionName,
                                self.DefaultRegionId)
        self.region = region
        if sdk_version:
            self.SDKVersion = sdk_version

        self.ECSSDK = 'aliyunsdkecs.request.v' + self.SDKVersion.replace('-', '')

        super(ECSConnection, self).__init__(acs_access_key_id=acs_access_key_id,
                                            acs_secret_access_key=acs_secret_access_key,
                                            region=self.region, product=self.ECSSDK,
                                            security_token=security_token, user_agent=user_agent)

    def build_filter_params(self, params, filters):
        if not isinstance(filters, dict):
            return

        flag = 1
        for key, value in filters.items():
            acs_key = key
            if acs_key.startswith('tag:'):
                while ('set_Tag%dKey' % flag) in params:
                    flag += 1
                if flag < 6:
                    params['set_Tag%dKey' % flag] = acs_key[4:]
                    params['set_Tag%dValue' % flag] = filters[acs_key]
                flag += 1
                continue
            if key == 'group_id':
                if not value.startswith('sg-') or len(value) != 12:
                    warnings.warn("The group-id filter now requires a security group "
                                  "identifier (sg-*) instead of a security group ID. "
                                  "The group-id " + value + "may be invalid.",
                                  UserWarning)
                params['set_SecurityGroupId'] = value
                continue
            if not isinstance(value, dict):
                acs_key = ''.join(s.capitalize() for s in acs_key.split('_'))
                params['set_' + acs_key] = value
                continue

            self.build_filters_params(params, value)

    # Instance methods

    def get_all_instances(self, instance_ids=None, filters=None, max_results=None):
        """
        Retrieve all the instance associated with your account. 

        :rtype: list
        :return: A list of  :class:`footmark.ecs.instance`

        """
        warnings.warn(('The current get_all_instances implementation will be '
                       'replaced with get_all_instances.'),
                      PendingDeprecationWarning)

        try:
            params = {}
            if instance_ids:
                self.build_list_params(params, instance_ids, 'InstanceIds')
            if filters:
                self.build_filter_params(params, filters)
            if max_results is not None:
                params['MaxResults'] = max_results
            instances = self.get_list('DescribeInstances', params, ['Instances', Instance])
            for inst in instances:
                filters = {}
                filters['instance_id'] = inst.id
                volumes = self.get_all_volumes(filters=filters)
                block_device_mapping = {}
                for vol in volumes:
                    block_device_mapping[vol.id] = vol
                setattr(inst, 'block_device_mapping', block_device_mapping)
                if inst.security_group_ids:
                    group_ids = []
                    for sg_id in inst.security_group_ids['security_group_id']:
                        group_ids.append(str(sg_id))
                        security_groups = self.get_all_security_groups(group_ids=group_ids)
                        setattr(inst, 'security_groups', security_groups)
        except ServerException as e:
            raise e
        except Exception as e:
            raise e

        return instances

    def describe_instances(self, instance_ids=None, filters=None, max_results=None):
        """
        Retrieve all the instance associated with your account.

        :rtype: list
        :return: A list of  :class:`footmark.ecs.instance`

        """
        warnings.warn(('The current get_all_instances implementation will be '
                       'replaced with get_all_instances.'),
                      PendingDeprecationWarning)

        params = {}

        if instance_ids:
            self.build_list_params(params, instance_ids, 'InstanceIds')
        if filters:
            self.build_filter_params(params, filters)
        if max_results is not None:
            params['MaxResults'] = max_results

        try:
            instances = self.get_list('DescribeInstances', params, ['Instances', Instance])
        except Exception as ex:
            instances = None

        return instances

    def start_instances(self, instance_ids=None):
        """
        Start the instances specified

        :type instance_ids: list
        :param instance_ids: A list of strings of the Instance IDs to start

        :rtype: list
        :return: A list of the instances started
        """
        params = {}
        results = []
        if instance_ids:
            if isinstance(instance_ids, six.string_types):
                instance_ids = [instance_ids]
            for instance_id in instance_ids:
                self.build_list_params(params, instance_id, 'InstanceId')
                if self.get_status('StartInstance', params):
                    results.append(instance_id)
        return results

    def stop_instances(self, instance_ids=None, force=False):
        """
        Stop the instances specified

        :type instance_ids: list
        :param instance_ids: A list of strings of the Instance IDs to stop

        :type force: bool
        :param force: Forces the instance to stop

        :rtype: list
        :return: A list of the instances stopped
        """
        params = {}
        results = []
        if force:
            self.build_list_params(params, 'true', 'ForceStop')
        if instance_ids:
            if isinstance(instance_ids, six.string_types):
                instance_ids = [instance_ids]
            for instance_id in instance_ids:
                self.build_list_params(params, instance_id, 'InstanceId')
                self.get_status('StopInstance', params)

            for instance_id in instance_ids:
                if self.wait_for_instance_status(instance_id, "Stopped"):
                    results.append(instance_id)
        return results

    def reboot_instances(self, instance_ids=None, force=False):
        """
        Reboot the specified instances.

        :type instance_ids: list
        :param instance_ids: The instances to terminate and reboot

        :type force: bool
        :param force: Forces the instance to stop

        """
        params = {}
        results = []
        if force:
            self.build_list_params(params, 'true', 'ForceStop')
        if instance_ids:
            if isinstance(instance_ids, six.string_types):
                instance_ids = [instance_ids]
            for instance_id in instance_ids:
                self.build_list_params(params, instance_id, 'InstanceId')
                self.get_status('RebootInstance', params)

            for instance_id in instance_ids:
                if self.wait_for_instance_status(instance_id, "Running"):
                    results.append(instance_id)

        return results

    def terminate_instances(self, instance_ids=None, force=False):
        """
        Terminate the instances specified

        :type instance_ids: list
        :param instance_ids: A list of strings of the Instance IDs to terminate

        :type force: bool
        :param force: Forces the instance to stop

        :rtype: list
        :return: A list of the instance_ids terminated
        """
        params = {}
        result = []
        if force:
            self.build_list_params(params, 'true', 'Force')
        if instance_ids:
            if isinstance(instance_ids, six.string_types):
                instance_ids = [instance_ids]
            for instance_id in instance_ids:
                self.build_list_params(params, instance_id, 'InstanceId')
                if self.delete_object_retry('DeleteInstance', params):
                    result.append(instance_id)
        return result

    def get_all_volumes(self, volume_ids=None, filters=None):
        """
        Get all Volumes associated with the current credentials.

        :type volume_ids: list
        :param volume_ids: Optional list of volume ids.  If this list
                           is present, only the volumes associated with
                           these volume ids will be returned.

        :type filters: dict
        :param filters: Optional filters that can be used to limit
                        the results returned.  Filters are provided
                        in the form of a dictionary consisting of
                        filter names as the key and filter values
                        as the value.  The set of allowable filter
                        names/values is dependent on the request
                        being performed.  Check the ECS API guide
                        for details.

        :type dry_run: bool
        :param dry_run: Set to True if the operation should not actually run.

        :rtype: list of Volume
        :return: The requested Volume objects
        """
        params = {}
        if volume_ids:
            self.build_list_params(params, volume_ids, 'DiskIds')
        if filters:
            self.build_filter_params(params, filters)
        return self.get_list('DescribeDisks', params, ['Disks', Disk])

    def create_instance(self, image_id, instance_type, group_id=None, zone_id=None, instance_name=None,
                        description=None, internet_data=None, host_name=None, password=None, io_optimized=None,
                        system_disk=None, disks=None, vswitch_id=None, private_ip=None, count=None,
                        allocate_public_ip=None, bind_eip=None, instance_charge_type=None, period=None, auto_renew=None,
                        auto_renew_period=None, instance_tags=None, ids=None, wait=None, wait_timeout=None):
        """
        create an instance in ecs

        :type image_id: string
        :param image_id: ID of an image file, indicating an image selected
            when an instance is started

        :type instance_type: string
        :param instance_type: Type of the instance

        :type group_id: string
        :param group_id: ID of the security group to which a newly created
            instance belongs

        :type zone_id: string
        :param zone_id: ID of a zone to which an instance belongs. If it is
            null, a zone is selected by the system

        :type instance_name: string
        :param instance_name: Display name of the instance, which is a string
            of 2 to 128 Chinese or English characters. It must begin with an
            uppercase/lowercase letter or a Chinese character and can contain
            numerals, “.”, “_“, or “-“.

        :type description: string
        :param description: Description of the instance, which is a string of
            2 to 256 characters.

        :type internet_data: list
        :param internet_data: It includes Internet charge type which can be
            PayByTraffic or PayByBandwidth, max_bandwidth_in and max_bandwidth_out

        :type host_name: string
        :param host_name: Host name of the ECS, which is a string of at least
            two characters. “hostname” cannot start or end with “.” or “-“.
            In addition, two or more consecutive “.” or “-“ symbols are not
            allowed.

        :type password: string
        :param password: Password to an instance is a string of 8 to 30
            characters

        :type io_optimized: string
        :param io_optimized: values are (1) none: none I/O Optimized
            (2) optimized: I/O Optimized

        :type system_disk: list
        :param system_disk: It includes disk_category, disk_size,
            disk_name and disk_description

        :type disks: list
        :param disks: It includes device_category, device_size,
            device_name, device_description, delete_on_termination
            and snapshot

        :type vswitch_id: string
        :param vswitch_id: When launching an instance in VPC, the
            virtual switch ID must be specified

        :type private_ip: string
        :param private_ip: Private IP address of the instance, which cannot be specified separately.

        :type count: integer
        :param count: Create No. of Instances

        :type allocate_public_ip: bool
        :param allocate_public_ip: Allocate Public IP Address to Instance

        :type bind_eip: string
        :param bind_eip: Bind Elastic IP Address

        :type instance_charge_type: string
        :param instance_charge_type: instance charge type

        :type: period: integer
        :param period: The time that you have bought the resource,
            in month. Only valid when InstanceChargeType is set as
            PrePaid. Value range: 1 to 12

        :type: auto_renew: bool
        :param auto_renew: Whether automatic renewal is supported.
            Only valid when InstanceChargeType is set PrePaid. Value
            range True: indicates to automatically renew
                  False，indicates not to automatically renew
            Default value: False.

        :type: auto_renew_period: int
        :param auto_renew_period: The period of each automatic renewal. Required when AutoRenew is True.
        The value must be the same as the period of the created instance.

        :type: ids: list
        :param ids: A list of identifier for this instance or set of
            instances, so that the module will be idempotent with
            respect to ECS instances.

        :type instance_tags: list
        :param instance_tags: A list of hash/dictionaries of instance
            tags, '[{tag_key:"value", tag_value:"value"}]', tag_key
            must be not null when tag_value isn't null

        :type wait: string
        :param wait: after execution of method whether it has to wait for some time interval

        :type wait_timeout: int
        :param wait_timeout: time interval of waiting

        :rtype: dict
        :return: Returns a dictionary of instance information about
            the instances started/stopped. If the instance was not
            able to change state, "changed" will be set to False.
            Note that if instance_ids and instance_tags are both non-
            empty, this method will process the intersection of the two

        """

        params = {}
        results = []
        changed = False

        # Datacenter Zone ID
        if zone_id:
            self.build_list_params(params, zone_id, 'ZoneId')

        # Operating System
        self.build_list_params(params, image_id, 'ImageId')

        # Instance Type
        self.build_list_params(params, instance_type, 'InstanceType')

        # Security Group
        if group_id:
            self.build_list_params(params, group_id, 'SecurityGroupId')

        # Instance Details
        if instance_name:
            self.build_list_params(params, instance_name, 'InstanceName')

        # Description of an instance
        if description:
            self.build_list_params(params, description, 'Description')

        # Internet Data
        if internet_data:
            if 'charge_type' in internet_data:
                self.build_list_params(params, internet_data[
                    'charge_type'], 'InternetChargeType')
            if 'max_bandwidth_in' in internet_data:
                self.build_list_params(params, internet_data[
                    'max_bandwidth_in'], 'InternetMaxBandwidthIn')
            if 'max_bandwidth_out' in internet_data:
                self.build_list_params(params, internet_data[
                    'max_bandwidth_out'], 'InternetMaxBandwidthOut')

        # Security Setup
        if host_name:
            self.build_list_params(params, host_name, 'HostName')

        # Password to an instance
        if password:
            self.build_list_params(params, password, 'Password')

        # input/output optimized
        if io_optimized is True:
            self.build_list_params(params, "optimized", 'IoOptimized')

        # Storage - Primary Disk
        if system_disk:
            if 'disk_category' in system_disk:
                self.build_list_params(params, system_disk[
                    'disk_category'], 'SystemDisk.Category')
            if 'disk_size' in system_disk:
                self.build_list_params(params, system_disk[
                    'disk_size'], 'SystemDisk.Size')
            if 'disk_name' in system_disk:
                self.build_list_params(params, system_disk[
                    'disk_name'], 'SystemDisk.DiskName')
            if 'disk_description' in system_disk:
                self.build_list_params(params, system_disk[
                    'disk_description'], 'SystemDisk.Description')

        # Disks Details
        disk_no = 1
        if disks:
            for disk in disks:
                if disk:
                    if 'disk_size' in disk:
                        self.build_list_params(params, disk['disk_size'], 'DataDisk' + str(disk_no) + 'Size')
                    if 'disk_category' in disk:
                        self.build_list_params(params, disk['disk_category'], 'DataDisk' + str(disk_no) + 'Category')
                    if 'snapshot_id' in disk:
                        self.build_list_params(params, disk['snapshot_id'], 'DataDisk' + str(disk_no) + 'SnapshotId')
                    if 'disk_name' in disk:
                        self.build_list_params(
                            params, disk['disk_name'], 'DataDisk' + str(disk_no) + 'DiskName')
                    if 'disk_description' in disk:
                        self.build_list_params(params, disk['disk_description'],
                                               'DataDisk' + str(disk_no) + 'Description')
                    if 'delete_on_termination' in disk:
                        self.build_list_params(params, disk['delete_on_termination'],
                                               'DataDisk' + str(disk_no) + 'DeleteWithInstance')
                    disk_no += 1

        # VPC Switch Id
        if vswitch_id:
            self.build_list_params(params, vswitch_id, 'VSwitchId')

        # Private Ip\P
        if private_ip:
            self.build_list_params(params, private_ip, 'PrivateIpAddress')

        if instance_charge_type:
            self.build_list_params(params, instance_charge_type, 'InstanceChargeType')

            # when charge type is PrePaid add Period and Auto Renew Parameters
            if instance_charge_type == 'PrePaid':

                # period of an Instance
                if period:
                    self.build_list_params(params, period, 'Period')

                    # auto renewal of instance
                    if auto_renew:
                        self.build_list_params(params, auto_renew, 'AutoRenew')
                        self.build_list_params(params, auto_renew_period, 'AutoRenewPeriod')

        # Instance Tags
        tag_no = 1
        if instance_tags:
            for instance_tag in instance_tags:
                if instance_tag:
                    if 'tag_key' and 'tag_value' in instance_tag:
                        if (instance_tag['tag_key'] is not None) and (instance_tag['tag_value'] is not None):
                            self.build_list_params(params, instance_tag[
                                'tag_key'], 'Tag' + str(tag_no) + 'Key')
                            self.build_list_params(params, instance_tag[
                                'tag_value'], 'Tag' + str(tag_no) + 'Value')
                            tag_no += 1

        # Client Token
        if ids:
            if len(ids) == count:
                self.build_list_params(params, ids, 'ClientToken')

        instances = []

        for i in range(count):
            # CreateInstance method call, returns newly created instanceId
            try:
                result = self.get_object('CreateInstance', params, ResultSet)
                instance_id = result.instance_id
                results.append({"instance_id": instance_id})
                changed = True

                self.wait_for_instance_status(instance_id, "Stopped")
                # Allocate allocate public ip
                if allocate_public_ip:
                    allocate_public_ip_params = {}
                    self.build_list_params(allocate_public_ip_params, instance_id, 'InstanceId')
                    self.get_status('AllocatePublicIpAddress', allocate_public_ip_params)
                # Allocate EIP Address
                if bind_eip:
                    allocate_eip_params = {}
                    self.build_list_params(
                        allocate_eip_params, bind_eip, 'AllocationId')
                    self.build_list_params(
                        allocate_eip_params, instance_id, 'InstanceId')
                    self.get_status('AssociateEipAddress', allocate_eip_params)

                # Start newly created Instance
                self.start_instances(instance_id)
                # get instance in running mode
                self.wait_for_instance_status(instance_id, "Running")

                instances.append(self.get_instance_details(instance_id))

            except ECSResponseError as e:
                results.append({"Error Code": e.error_code, "Error Message": e.message,
                                "RequestId": e.request_id, "Http Status": e.http_status})
            except Exception as e:
                results.append({"Error": e})

        # if str(wait).lower() in ['yes', 'true'] and wait_timeout:
        #     time.sleep(wait_timeout)

        return changed, instances, results

    def modify_instance(self, attributes=None):
        """
        modify the instance attributes such as name, description, password and host_name

        :type: list
        :param attributes: A list of dictionary of instance attributes which includes
            id, name, description, password and host_name
        :return: A list of the instance_ids modified
        """
        results = []
        changed = False
        if attributes:
            for attribute in attributes:
                if attribute:
                    params = {}
                    if 'id' in attribute:
                        self.build_list_params(params, attribute['id'], 'InstanceId')
                    if 'name' in attribute:
                        self.build_list_params(params, attribute['name'], 'InstanceName')
                    if 'description' in attribute:
                        self.build_list_params(params, attribute['description'], 'Description')
                    if 'password' in attribute:
                        self.build_list_params(params, attribute['password'], 'Password')
                    if 'host_name' in attribute:
                        self.build_list_params(params, attribute['host_name'], 'HostName')

                    try:
                        changed = self.get_status('ModifyInstanceAttribute', params)
                        if 'password' in attribute:
                            self.reboot_instances(instance_ids=[attribute['id']], force=True)
                            self.wait_for_instance_status(attribute['id'], "Running")
                        if changed:
                            results.append("Instance %s attribute has been modified successfully.")
                    except ServerException as e:
                        results.append({"Error Code": e.error_code, "Error Message": e.message,
                                        "RequestId": e.request_id, "Http Status": e.http_status})
                    except Exception as e:
                        results.append({"Error:": e})

        return changed, results

    def get_instance_status(self, zone_id=None, pagenumber=None, pagesize=None):
        """
        Get status of instance

        :type zone_id: string
        :param zone_id: Optional parameter. ID of the zone to which an instance belongs

        :type pagenumber: integer
        :param pagenumber: Page number of the instance status list. The start value is 1. The default value is 1

        :type pagesize: integer
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50.
        The default value is 10

        :rtype: json
        :return: The result of passed instances
        """

        params = {}
        results = []

        if zone_id:
            self.build_list_params(params, zone_id, 'ZoneId')
        if pagenumber:
            self.build_list_params(params, pagenumber, 'PageNumber')
        if pagesize:
            self.build_list_params(params, pagesize, 'PageSize')

        try:
            results = self.get_object('DescribeInstanceStatus', params, ResultSet)
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error": e})

        return False, results

    def join_security_group(self, instance_ids, group_id):
        """
        Assign an existing instance to a pre existing security group

        :type instance_ids: List
        :param instance_ids: The list of instance id's which are to be assigned to the security group

        :type group_id: dict
        :param group_id: ID of the security group to which a instance is to be added

        :return: Success message, confirming joining security group or error message if any
        """
        results = []
        success_instance_ids = []
        failed_instance_ids = []
        changed = False

        if not isinstance(instance_ids, list):
            results.append({"Error Message": "The specified instance_ids must be of type list"})
            return changed, results, success_instance_ids, failed_instance_ids

        for inst in instance_ids:
            params = {}
            # Instance Id, which is to be added to a security group
            self.build_list_params(params, inst, 'InstanceId')

            # Security Group ID, an already existing security group, to which instance is added
            self.build_list_params(params, group_id, 'SecurityGroupId')

            # Method Call, to perform adding action
            try:
                self.get_status('JoinSecurityGroup', params)

                # Verifying whether operation got performed successfully
                changed = self.verify_join_remove_securitygrp(inst, group_id, 'join')
                if changed:
                    success_instance_ids.append(inst)

            except ServerException as e:
                failed_instance_ids.append(inst)
                results.append({"Error Code": e.error_code, "Error Message": e.message,
                                "RequestId": e.request_id, "Http Status": e.http_status})
            except Exception as e:
                failed_instance_ids.append(inst)
                results.append({"Error": e})

        return changed, results, success_instance_ids, failed_instance_ids

    def leave_security_group(self, instance_ids, group_id):
        """
        Remove an existing instance from given security group

        :type instance_ids: List
        :param instance_ids: The list of instance id's which are to be assigned to the security group

        :type group_id: dict
        :param group_id: ID of the security group to which a instance is to be added

        :return: Success message, confirming joining security group or error message if any
        """
        params = {}
        results = []
        success_instance_ids = []
        failed_instance_ids = []
        changed = False

        if not isinstance(instance_ids, list):
            results.append({"Error Message": "The specified instance_ids must be of type list"})
            return changed, results, success_instance_ids, failed_instance_ids

        # Security Group ID, an already existing security group, from which instance is removed
        self.build_list_params(params, group_id, 'SecurityGroupId')
        for inst in instance_ids:
            # Instance Id to be removed from a security group
            self.build_list_params(params, inst, 'InstanceId')

            # Method Call, to perform adding action
            try:
                self.get_status('LeaveSecurityGroup', params)
                # Verifying whether operation got performed successfully
                changed = self.verify_join_remove_securitygrp(inst, group_id, 'remove')
                if changed:
                    success_instance_ids.append(inst)

            except ServerException as e:
                failed_instance_ids.append(inst)
                results.append({"Error Code": e.error_code, "Error Message": e.message,
                                "RequestId": e.request_id, "Http Status": e.http_status})
            except Exception as e:
                failed_instance_ids.append(inst)
                results.append({"Error": e})

        return changed, results, success_instance_ids, failed_instance_ids

    def create_security_group(self, group_name=None, description=None, group_tags=None, vpc_id=None):
        """
        create and authorize security group in ecs

        :type group_name: string
        :param group_name: Name of the security group

        :type description: string
        :param description: Description of the security group

        :type group_tags: list
        :param group_tags: A list of hash/dictionaries of disk
            tags, '[{tag_key:"value", tag_value:"value"}]', tag_key
            must be not null when tag_value isn't null

        :type vpc_id: string
        :param vpc_id: The ID of the VPC to which the security group belongs

        :rtype: dict
        :return: Returns a dictionary of group information about
            the the group created/authorized. If the group was not
            created and authorized, "changed" will be set to False.
        """

        params = {}
        results = []
        changed = False
        security_group_id = None

        # Security Group Name
        self.build_list_params(params, group_name, 'SecurityGroupName')

        # Security Group VPC Id
        if vpc_id:
            self.build_list_params(params, vpc_id, 'VpcId')

        # Security Group Description
        self.build_list_params(params, description, 'Description')

        # Instance Tags
        tagno = 1
        if group_tags:
            for group_tag in group_tags:
                if group_tag:
                    if 'tag_key' in group_tag:
                        self.build_list_params(params, group_tag[
                            'tag_key'], 'Tag' + str(tagno) + 'Key')
                    if 'tag_value' in group_tag:
                        self.build_list_params(params, group_tag[
                            'tag_value'], 'Tag' + str(tagno) + 'Value')
                    tagno = tagno + 1

        # CreateSecurityGroup method call, returns newly created security group id
        response = self.get_object('CreateSecurityGroup', params, ResultSet)
        if response:
            return self.get_security_group_attribute(group_id=response.security_group_id)

        return None

    def authorize_security_group(self, security_group_id=None, inbound_rules=None, outbound_rules=None):
        """
        authorize security group in ecs

        :type security_group_id: string
        :param security_group_id: The ID of the target security group

        :type inbound_rules: list
        :param inbound_rules: Inbound rules for authorization

        :type outbound_rules: list
        :param outbound_rules: Outbound rules for authorization

        :rtype: list
        :return: Returns the successful message if all rules successfully authorized else returns details of failed
                    authorization rules.

        Note: Use validate_sg_rules(rules) method for pre-defined basic validation before using this method.
        """

        # aliases for rule

        rule_types = []
        inbound_failed_rules = []
        outbound_failed_rules = []

        api_action = {
            "inbound": "AuthorizeSecurityGroup",
            "outbound": "AuthorizeSecurityGroupEgress"
        }

        rule_choice = {
            "inbound": inbound_rules,
            "outbound": outbound_rules,
        }

        api_group_id_param_name = {
            "inbound": "SourceGroupId",
            "outbound": "DestGroupId",
        }

        api_group_owner_param_name = {
            "inbound": "SourceGroupOwnerId",
            "outbound": "DestGroupOwnerId",
        }

        api_cidr_ip_param_name = {
            "inbound": "SourceCidrIp",
            "outbound": "DestCidrIp",
        }

        failure_rule_choice = {
            "inbound": inbound_failed_rules,
            "outbound": outbound_failed_rules
        }

        if inbound_rules:
            rule_types.append('inbound')

        if outbound_rules:
            rule_types.append('outbound')

        result_details = []

        for rule_type in rule_types:

            rules = rule_choice.get(rule_type)

            total_rules = len(rules)

            success_rule_count = 0

            if total_rules != 0:

                for rule in rules:

                    params = {}

                    self.build_list_params(params, security_group_id, 'SecurityGroupId')

                    ip_protocol = rule['ip_protocol']

                    self.build_list_params(params, ip_protocol, 'IpProtocol')

                    port_range = str(rule['port_range'])

                    self.build_list_params(params, port_range, 'PortRange')

                    if 'group_id' in rule:
                        self.build_list_params(params, rule['group_id'], api_group_id_param_name.get(rule_type))

                    if 'cidr_ip' in rule:
                        self.build_list_params(params, rule['cidr_ip'], api_cidr_ip_param_name.get(rule_type))

                    if 'group_owner_id' in rule:
                        self.build_list_params(params, rule['group_owner_id'],
                                               api_group_owner_param_name.get(rule_type))

                    if 'policy' in rule:
                        self.build_list_params(params, rule['policy'], 'Policy')
                    if 'priority' in rule:
                        self.build_list_params(params, rule['priority'], 'Priority')
                    if 'nic_type' in rule:
                        self.build_list_params(params, rule['nic_type'], 'NicType')

                    try:
                        if self.get_status(api_action.get(rule_type), params):
                            success_rule_count += 1

                    except Exception as ex:
                        error_code = ex.error_code
                        msg = ex.message

                        rule['Error Code'] = error_code
                        rule['Error Message'] = msg

                        failure_rule_choice.get(rule_type).append(rule)

                        result_details.append(
                            'Error: ' + rule_type + ' rule authorization failed for protocol ' + ip_protocol +
                            ' with port range ' + port_range)

                if success_rule_count == total_rules:
                    result_details.append(
                        rule_type + ' rule authorization successful for group id ' + security_group_id)

        return inbound_failed_rules, outbound_failed_rules, result_details

    def get_security_group_attribute(self, group_id=None, nic_type=None, direction='all'):
        """
        Querying Security Group List returns the basic information about all
              user-defined security groups.

        :type  group_id: String
        :param group_id: ID of security groups id

        :type nic_type: String
        :param nic_type: Network type of security group. The choice value is 'internet' or 'intranet'.

        :type direction: String
        :param direction: The direction of security group rule. The choice value is 'egress', 'ingress' or 'all', and 'all' is default.

        :rtype: dict
        :return: Returns a dictionary of security group information

                """

        params = {}
        if group_id:
            self.build_list_params(params, group_id, 'SecurityGroupId')
        if nic_type:
            self.build_list_params(params, nic_type, 'NicType')
        if direction:
            self.build_list_params(params, direction, 'Direction')

        return self.get_object('DescribeSecurityGroupAttribute', params, SecurityGroup)

    def get_all_security_groups(self, group_ids=None, vpc_id=None, filters=None):
        """
        Get all security groups associated with your account in a region.
    
        :type group_ids: list
        :param group_ids: A list of IDs of security groups to retrieve for
                          security groups within a VPC.
                          
        :type vpc_id: string
        :param vpc_id: ID of vpc which security groups belong.
    
        :type filters: dict
        :param filters: Optional filters that can be used to limit
                        the results returned.  Filters are provided
                        in the form of a dictionary consisting of
                        filter names as the key and filter values
                        as the value.  The set of allowable filter
                        names/values is dependent on the request
                        being performed.  Check the ECS API guide
                        for details.
    
        :rtype: list
        :return: A list of SecurityGroup
        """
        params = {}
        groups = []
        if group_ids:
            self.build_list_params(params, group_ids, 'SecurityGroupIds')
        if vpc_id:
            self.build_list_params(params, vpc_id, 'VpcId')
        if filters:
            self.build_filter_params(params, filters)
        results = self.get_list('DescribeSecurityGroups', params, ['SecurityGroups', SecurityGroup])
        if results:
            for group in results:
                groups.append(self.get_security_group_attribute(group_id=group.id))

            return groups
        return results

    def delete_security_group(self, group_ids):
        """
        Delete Security Group , delete security group inside particular region.

        :type  group_ids: dict
        :param group_ids: The Security Group ID

        :rtype: string
        :return: A method return result of after successfully deletion of security group
        """
        # Call DescribeSecurityGroups method to get response for all running instances
        params = {}
        results = []
        for group_id in group_ids:
            if group_id:
                self.build_list_params(params, group_id, 'SecurityGroupId')
                self.get_status('DeleteSecurityGroup', params)
                results.append(group_id)

        return results

    def create_disk(self, zone_id, disk_name=None, description=None,
                    disk_category=None, size=None, disk_tags=None,
                    snapshot_id=None):
        """
        create an disk in ecs

        :type zone_id: string
        :param zone_id: ID of a zone to which an instance belongs.

        :type disk_name: string
        :param disk_name: Display name of the disk, which is a string
            of 2 to 128 Chinese or English characters.

        :type description: string
        :param description: Description of the disk, which is a string of
            2 to 256 characters.

        :type disk_category: string
        :param disk_category: Displays category of the data disk
                Optional values are:
                Cloud - general cloud disk
                cloud_efficiency - efficiency cloud disk
                cloud_ssd - cloud SSD
                Default value:cloud

        :type size: integer
        :param size: Size of the system disk, in GB, values range:
                Cloud - 5 ~ 2000
                cloud_efficiency - 20 ~ 2048
                cloud_ssd - 20 ~ 2048
                The value should be equal to or greater than the size of the specific SnapshotId.

        :type disk_tags: list
        :param disk_tags: A list of hash/dictionaries of instance
            tags, '[{tag_key:"value", tag_value:"value"}]', tag_key
            must be not null when tag_value isn't null        

        :type snapshot_id: integer
        :param snapshot_id: Snapshots are used to create the data disk
            After this parameter is specified, Size is ignored.

        :rtype: dict
        :return: Returns a dictionary of disk information
        """
        params = {}
        results = []
        changed = False
        disk_id = None

        # Zone Id
        self.build_list_params(params, zone_id, 'ZoneId')

        # DiskName
        if disk_name:
            self.build_list_params(params, disk_name, 'DiskName')

        # Description of disk
        if description:
            self.build_list_params(params, description, 'Description')

        # Disk Category
        if disk_category:
            self.build_list_params(params, disk_category, 'DiskCategory')

        # Size of Disk
        if size:
            self.build_list_params(params, size, 'Size')

            # Disk Tags
        tag_no = 1
        if disk_tags:
            for disk_tag in disk_tags:
                if disk_tag:
                    if 'tag_key' and 'tag_value' in disk_tag:
                        if (disk_tag['tag_key'] is not None) and (disk_tag['tag_value'] is not None):
                            self.build_list_params(params, disk_tag[
                                'tag_key'], 'Tag' + str(tag_no) + 'Key')
                            self.build_list_params(params, disk_tag[
                                'tag_value'], 'Tag' + str(tag_no) + 'Value')
                            tag_no += 1

                            # Snapshot Id
        if snapshot_id:
            self.build_list_params(params, snapshot_id, 'SnapshotId')

        try:
            rs = self.get_object('CreateDisk', params, ResultSet)
            results.append("Disk Creation Successful")
            changed = True
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error:": e})

        return changed, str(rs.disk_id), results

    def attach_disk(self, disk_id, instance_id, delete_with_instance=None):
        """
        Method to attach a disk to instance

        :type instance_id: string
        :param instance_id: The instance's ID

        :type disk_id: string
        :param disk_id: The disk ID in the cloud

        :type delete_with_instance: string
        :param delete_with_instance: value depicting should disk be deleted with instance.

        :return: A list of the total number of security groups, region ID of the security group,
                 the ID of the VPC to which the security group belongs
        """
        params = {}
        results = []
        changed = False

        if not instance_id:
            results.append({"Error": "Disk %s is not attached to any instance, instance id: %s" % (disk_id, instance_id)})
            return changed, results

        _, disk_status, _, result = self.retrieve_instance_for_disk(disk_id)

        if result:
            return changed, result
        if disk_status and str(disk_status).strip().lower() != "available":
            results.append({"Error": "The disk %s status %s does not support to operate attachment." % (disk_id, disk_status)})
            return changed, results

        # Instance Id, which is used to attach disk
        self.build_list_params(params, instance_id, 'InstanceId')

        # Disk Id, the disk_id to be mapped
        self.build_list_params(params, disk_id, 'DiskId')

        # should the disk be deleted with instance
        if delete_with_instance:
            if str(delete_with_instance).lower().strip() == 'yes':
                delete_with_instance = 'true'
            elif str(delete_with_instance).lower().strip() == 'no':
                delete_with_instance = 'false'
            else:
                delete_with_instance = str(delete_with_instance).lower().strip()

            self.build_list_params(params, delete_with_instance, 'DeleteWithInstance')

        # Method Call, to perform adding action
        try:
            if self.get_status('AttachDisk', params):
                changed, result = self.wait_for_disk_status(disk_id=disk_id, disk_status="in_use")
                if not changed:
                    results.append(result)
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error": e})

        return changed, results

    def detach_disk(self, disk_id):
        """
        Method to detach a disk to instance

        :type disk_id: dict
        :param disk_id: ID of Disk for attaching detaching disk

        :return: Return status of Operation
        """
        params = {}
        changed = False
        # region retrieve InstanceId from DiskId
        instance_id, _, disk_portable, results = self.retrieve_instance_for_disk(disk_id)

        if results:
            return changed, results, instance_id

        if not disk_portable:
            results.append({"Error Message": "The disk %s can be detached, and its portable is %s." % (disk_id, disk_portable)})
            return changed, results, instance_id

        if not instance_id:
            results.append({"Error Message": "Disk %s is not attached to any instance, instance id: %s" % (disk_id, instance_id)})
            return changed, results, instance_id

        # Instance Id, which is to be added to a detach disk
        self.build_list_params(params, instance_id, 'InstanceId')

        # Disk Id, the disk_id to be mapped
        self.build_list_params(params, disk_id, 'DiskId')

        try:
            if self.get_status('DetachDisk', params):
                changed, result = self.wait_for_disk_status(disk_id=disk_id, disk_status="available")
                if not changed:
                    results.append(result)
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error": e})

        return changed, results, instance_id

    def retrieve_instance_for_disk(self, disk_id):
        # method is used to retrieve instance_id from disk_id, it is required in detach disk.
        # In detach disk instance id is retrieved from disk, it is not taken from ansible.
        results = []

        instance_id = None
        disk_portable = None
        disk_status = None
        disks = None
        try:
            disks = self.get_all_volumes([disk_id])
            if not disks or len(disks) < 1 or not disks[0]:
                return False, {"Error": "The specified disk %s is not found." % disk_id}

            # wait until disk status becomes specified
            if disk_status == str(disks[0].status).strip().lower():
                return True, None

            disk = disks[0]
            instance_id = str(disk.instance_id)
            disk_portable = str(disk.portable)
            disk_status = str(disk.status)

        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error Message::::": e, "disks::::": disks.disks})

        return instance_id, disk_status, disk_portable, results

    def delete_disk(self, disk_id):
        """
        Method to delete a disk

        :type disk_id: dict
        :param disk_id: ID of Disk for attaching detaching disk

        :return: Return status of Operation
        """
        params = {}
        results = []
        changed = False

        # the disk to be deleted
        self.build_list_params(params, disk_id, 'DiskId')

        try:
            # check disk exist or not
            disk_list = self.get_all_volumes(volume_ids=[disk_id])

            if len(disk_list) > 0:
                changed = self.delete_object_retry('DeleteDisk', params)
            else:
                results.append({"Error Message": "Disk %s is not found, and deleting it failed." % disk_id})
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error": e})
        return changed, results

    def create_image(self, snapshot_id=None, image_name=None, image_version=None, description=None,
                     images_tags=None, instance_id=None, disk_mapping=None, launch_permission=None,
                     wait=None, wait_timeout=None):
        """
        Create a user-defined image with snapshots of system disks.
        The created image can be used to create a new ECS instance.

        :type snapshot_id: string
        :param snapshot_id: A user-defined image is created from the specified snapshot.

        :type image_name: string
        :param image_name: image name which is to be created

        :type image_version: string
        :param image_version: version of image

        :type description: string
        :param description: description of the image

        :type images_tags: list
        :param images_tags: tags for image

        :type instance_id: string
        :param instance_id: the specified instance_id

        :type disk_mapping: list
        :param disk_mapping: An optional list of device hashes/dictionaries with custom configurations

        :type launch_permission: list
        :param launch_permission: An optional list of userIds who are permitted to launch ami

        :type wait: string
        :param wait: An optional bool value indicating wait for instance to be running before running

        :type wait_timeout: int
        :param wait_timeout: An optional int value indicating how long to wait, default 300

        :return: Image id
        """
        params = {}
        results = []
        changed = False
        image_id = ''
        request_id = ''

        # the snapshot id for creating image
        if snapshot_id:
            # Verifying progress of snapshot_id, snapshot_id should be 100% completed
            snapshot_results, snapshot_progress, snapshot_changed = self.get_snapshot_image(snapshot_id)

            if snapshot_results:
                if 'error code' in str(snapshot_results).lower():
                    results = snapshot_results
                    return changed, image_id, results, request_id

            if not snapshot_changed:
                results.append({"Error Code": "Snapshot.NotReady", "Error Message": "snapshot is not ready"})
                return changed, image_id, results, request_id

        if snapshot_id:
            self.build_list_params(params, snapshot_id, 'SnapshotId')

        # set the image name
        if image_name:
            self.build_list_params(params, image_name, 'ImageName')

        # set the image version
        if image_version:
            self.build_list_params(params, image_version, 'ImageVersion')

        # set the description
        if description:
            self.build_list_params(params, description, 'Description')

        # specify the instance id
        if instance_id:
            self.build_list_params(params, instance_id, 'InstanceId')

        # specify the disk device mapping, An optional list of device hashes/dictionaries with custom configurations
        if disk_mapping:
            mapping_no = 1
            for mapping in disk_mapping:
                if mapping:
                    if 'device' in mapping:
                        self.build_list_params(params, mapping[
                            'device'], 'DiskDeviceMapping.' + str(mapping_no) + '.Device')
                    if 'disk_size' in mapping:
                        self.build_list_params(params, mapping[
                            'disk_size'], 'DiskDeviceMapping.' + str(mapping_no) + '.Size')
                    if 'snapshot_id' in mapping:
                        self.build_list_params(params, mapping[
                            'snapshot_id'], 'DiskDeviceMapping.' + str(mapping_no) + '.SnapshotId')
                        snapshot_map_results, snapshot_map_progress, snapshot_map_changed \
                            = self.get_snapshot_image(mapping['snapshot_id'])
                        if snapshot_map_results:
                            if 'error code' in str(snapshot_map_results).lower():
                                results = snapshot_map_results
                                return changed, image_id, results, request_id

                        if not snapshot_map_changed:
                            results.append(
                                {"Error Code": "Snapshot.NotReady", "Error Message": "snapshot is not ready"})
                            return changed, image_id, results, request_id

                    mapping_no += 1

        # set the instance tags, maximum 5 tags
        tag_no = 1
        if images_tags:
            for instance_tag in images_tags:
                if instance_tag and tag_no < 6:
                    if 'tag_key' in instance_tag:
                        self.build_list_params(params, instance_tag[
                            'tag_key'], 'Tag' + str(tag_no) + 'Key')
                    if 'tag_value' in instance_tag:
                        self.build_list_params(params, instance_tag[
                            'tag_value'], 'Tag' + str(tag_no) + 'Value')
                    tag_no += 1

        try:
            response = self.get_status('CreateImage', params)

            if response:
                image_id = response['ImageId']
                request_id = response['RequestId']

            image_sharing_results = []
            if launch_permission and image_id:
                sharing_changed, image_sharing_results = self.set_launch_perms(launch_permission, image_id)

            if wait:
                if wait.lower() in ['yes', 'true']:
                    if not wait_timeout:
                        wait_timeout = 300
                    time.sleep(wait_timeout)

            results.append("Image creation successful")

            changed = True

            if image_sharing_results:
                if 'error code' in str(image_sharing_results).lower():
                    results.append(image_sharing_results)
                    changed = False
                else:
                    results.append(image_sharing_results)
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error:": e})

        return changed, image_id, results, request_id

    def set_launch_perms(self, launch_permission, image_id, operation_flag=True):
        """
        To set launch permissions
        i.e user accounts which have rights on image

        :type launch_permission: list
        :param launch_permission: list of userids, max 10 permitted at a time

        :type: image_id: string
        :param image_id: imageid to which to add user rights

        :type: operation_flag: bool
        :param operation_flag: True : add acount, False: remove account

        :return:
        """
        params = {}
        results = []
        changed = False

        if not image_id:
            results.append({"Error Code": "image_id is mandatory", "Error Message": "image_id is mandatory"})
            return None

        self.build_list_params(params, image_id, 'ImageId')
        if launch_permission:
            user_account_list = launch_permission
            if user_account_list:
                user_no = 1
                for account in range(0, len(user_account_list)):
                    self.build_list_params(params, user_account_list[account
                    ], 'AddAccount.' + str(user_no))
                    user_no += 1
                    if user_no == 11:
                        break
        try:
            response = self.get_status('ModifyImageSharePermission', params)
            changed = True
            results.append("launch permissions set successfully")
        except Exception as ex:
            error_code = ex.error_code
            error_msg = ex.message
            results.append("launch permissions not set successfully")
            results.append({"Error Code": error_code, "Error Message": error_msg})
            changed = False

        return changed, results

    def delete_image(self, image_id):
        """
        Delete image , delete image inside particular region.
        :type image_id: dict
        :param image_id: ID of an Image        
        :rtype: Return status of Operation
        """
        params = {}
        results = []
        changed = False

        self.build_list_params(params, image_id, 'ImageId')

        try:
            response = self.get_status('DescribeImages', params)
            if len(response) > 0:
                json_obj = response
                total_instance = json_obj['TotalCount']
                if total_instance > 0:
                    for items in json_obj['Images']['Image']:
                        if image_id == items['ImageId']:
                            response = self.get_status('DeleteImage', params)
                            results.append(response)
                            changed = True
                else:
                    results.append({"Error Code": "Image does not exist", "Error Message": "Image does not exist"})
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
            changed = False
        except Exception as e:
            results.append({"Error:": e})
            changed = False

        return changed, results

    def get_snapshot_image(self, snapshot_id):
        params = {}
        results = []
        progress = ''
        changed = False
        counter = 0
        try:
            while changed == False:
                self.build_list_params(params, [snapshot_id], 'SnapshotIds')

                if counter > 20:
                    break
                obtained_results = self.get_status('DescribeSnapshots', params)
                counter += 1
                if obtained_results and len(obtained_results['Snapshots']['Snapshot']) > 0:
                    status = obtained_results['Snapshots']['Snapshot'][0]['Status']
                    progress = obtained_results['Snapshots']['Snapshot'][0]['Progress']

                    if not '100%' in progress:
                        time.sleep(60)
                    else:
                        changed = True
                        progress = '100'
                        break
                else:
                    results.append({"Error Code": "Invalid.SnapshotId", "Error Message": "The snapshot id not found"})
                    break
        except ServerException as e:
            results.append({"Error Code": e.error_code, "Error Message": e.message,
                            "RequestId": e.request_id, "Http Status": e.http_status})
        except Exception as e:
            results.append({"Error:": e})

        return results, progress, changed

    def get_instance_details(self, instance_id):
        """
        Get details of an Instance
        :param instance_id: Id of an Instance
        :return: Return info about instance
        """
        params = {}
        results = []
        instance_details = None

        self.build_list_params(params, instance_id, 'InstanceId')

        return self.get_object('DescribeInstanceAttribute', params, Instance)

    # retry decorator
    def retry(ExceptionToCheck, tries=10, delay=30, backoff=2, logger=None):

        def deco_retry(f):

            @wraps(f)
            def f_retry(*args, **kwargs):
                mtries, mdelay = tries, delay
                while mtries > 1:
                    try:
                        return f(*args, **kwargs)
                    except ExceptionToCheck, e:
                        time.sleep(mdelay)
                        mtries -= 1
                        mdelay *= backoff
                return f(*args, **kwargs)

            return f_retry  # true decorator

        return deco_retry

    # Use retry decorator
    @retry(Exception, tries=10)
    def wait_for_instance_status(self, instance_id, status):
        try:
            instance = self.get_instance_details(instance_id)
            if instance:
                # wait until instance status is expected
                while instance.status not in [status, str(status).lower()]:
                    time.sleep(10)
                    instance = self.get_instance_details(instance_id)

        except Exception:
            raise Exception

    @retry(Exception, tries=3)
    def wait_for_disk_status(self, disk_id, disk_status):
        """
        To verify disk status has become expected after attaching or detaching disk
        """
        done = False
        try:
            while not done:
                time.sleep(3)
                disks = self.get_all_volumes([disk_id])
                if not disks or len(disks) < 1 or not disks[0]:
                    return False, {"Error": "The specified disk %s is not found." % disk_id}

                # wait until disk status becomes specified
                if disk_status == str(disks[0].status).strip().lower():
                    return True, None

        except Exception:
            raise Exception

    @retry(Exception, tries=4)
    def delete_object_retry(self, action, params):
        """
        Using retry to deleting disk when disk is 'Initializing'
        """
        done = False
        try:
            while not done:
                time.sleep(5)
                try:
                    done = self.get_status(action, params)
                except ServerException as e:
                    if str(e.error_code) == "IncorrectInstanceStatus.Initializing":
                        continue

        except Exception as ex:
            raise ex
        return done

    @retry(Exception, tries=3)
    def verify_join_remove_securitygrp(self, instance_id, group_id, mode):
        """
        To verify join & remove operations got performed in security group
        """
        done = False
        count = 0
        id_of_instance = [instance_id]
        try:
            while not done:
                time.sleep(5)
                instance_list = self.get_all_instances(id_of_instance, None, None)
                if len(instance_list) > 0:
                    if mode.lower() == 'join':
                        for inst in instance_list:
                            if len(inst.security_group_ids['security_group_id']) > 0:
                                for grp in inst.security_group_ids['security_group_id']:
                                    if str(grp) == group_id:
                                        done = True
                                        break

                    elif mode.lower() == 'remove':
                        for inst in instance_list:
                            if len(inst.security_group_ids['security_group_id']) > 0:
                                for grp in inst.security_group_ids['security_group_id']:
                                    if str(grp) == group_id:
                                        count = count + 1
                                if count == 0:
                                    done = True
                                    break
        except Exception as ex:
            raise ex

        return done

