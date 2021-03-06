# encoding: utf-8
import warnings
import time

from footmark.connection import ACSQueryConnection
from footmark.vpc.regioninfo import RegionInfo
from footmark.exception import VPCResponseError
from footmark.resultset import ResultSet
from footmark.vpc.vpc import Vpc
from footmark.vpc.eip import Eip
from footmark.vpc.vswitch import VSwitch
from footmark.vpc.router import RouteEntry, RouteTable
from footmark.vpc.config import *
from aliyunsdkcore.acs_exception.exceptions import ServerException


class VPCConnection(ACSQueryConnection):
    SDKVersion = '2014-05-26'
    DefaultRegionId = 'cn-hangzhou'
    DefaultRegionName = u'杭州'.encode("UTF-8")
    ResponseError = VPCResponseError

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

        self.VPCSDK = 'aliyunsdkecs.request.v' + self.SDKVersion.replace('-', '')

        super(VPCConnection, self).__init__(acs_access_key_id=acs_access_key_id,
                                            acs_secret_access_key=acs_secret_access_key,
                                            region=self.region, product=self.VPCSDK,
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

    def create_vpc(self, cidr_block=None, user_cidr=None, vpc_name=None, description=None, client_token=None,
                   wait_timeout=None, wait=None):

        """
        Create a ECS VPC (virtual private cloud) in Aliyun Cloud
        :type cidr_block: String
        :param cidr_block: The cidr block representing the VPC, e.g. 10.0.0.0/8
        :type user_cidr: String
        :param user_cidr: User custom cidr in the VPC
        :type vpc_name: String
        :param vpc_name: A VPC name
        :type description: String
        :param description: Description about VPC
        :type wait: string
        :param wait: An optional bool value indicating wait for instance to be running before running
        :type wait_timeout: int
        :param wait_timeout: An optional int value indicating how long to wait, default 300
        :return: Returns details of created VPC
        """

        params = {}
        timeout = 20

        if cidr_block:
            self.build_list_params(params, cidr_block, 'CidrBlock')

        if user_cidr:
            self.build_list_params(params, user_cidr, 'UserCidr')

        if vpc_name:
            self.build_list_params(params, vpc_name, 'VpcName')

        if description:
            self.build_list_params(params, description, 'Description')

        if client_token:
            self.build_list_params(params, client_token, 'ClientToken')
        response = self.get_object('CreateVpc', params, ResultSet)
        vpc_id = str(response.vpc_id)
        if str(wait).lower() in ['yes', 'true'] and wait_timeout:
            timeout = wait_timeout
        self.wait_for_vpc_status(vpc_id, 'Available', 4, timeout)

        return self.get_vpc_attribute(vpc_id)

    def get_vpc_attribute(self, vpc_id):
        """
        method to get all vpcId of particular region 
        :return: Return All vpcs in the region
        """
        vpcs = self.get_all_vpcs(vpc_id=vpc_id)
        if vpcs:
            return vpcs[0]

        return None

    def get_all_vpcs(self, vpc_id=None, is_default=None, pagenumber=1, pagesize=10):
        """
        Find Vpc in One Region
        :type vpc_id: string
        :param vpc_id: Vpc Id of the targeted Vpc to terminate
        :type is_default: bool
        :param is_default: The vpc created by system if it is True
        :type pagenumber: integer
        :param pagenumber: Page number of the instance status list. The start value is 1. The default value is 1
        :type pagesize: integer
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50.
        The default value is 10
        :rtype: list
        :return: Returns VPC list if vpcs found along with Vpc details.
        """
        params = {}

        if vpc_id:
            self.build_list_params(params, vpc_id, 'VpcId')

        if is_default is not None:
            self.build_list_params(params, is_default, 'IsDefault')

        self.build_list_params(params, pagenumber, 'PageNumber')
        self.build_list_params(params, pagesize, 'PageSize')

        return self.get_list('DescribeVpcs', params, ['Vpcs', Vpc])

    def modify_vpc(self, vpc_id, vpc_name=None, description=None, user_cidr=None, wait_timeout=None, wait=None):

        """
        Modify a ECS VPC's (virtual private cloud) attribute in Aliyun Cloud
        :type vpc_id: string
        :param vpc_id: Vpc Id of the targeted Vpc to modify
        :type vpc_name: String
        :param vpc_name: A VPC name
        :type description: String
        :param description: Description about VPC
        :type user_cidr: String
        :param user_cidr: User custom cidr in the VPC
        :type wait: string
        :param wait: An optional bool value indicating wait for instance to be running before running
        :type wait_timeout: int
        :param wait_timeout: An optional int value indicating how long to wait, default 300
        :return: Returns details of created VPC
        """

        params = {}
        self.build_list_params(params, vpc_id, 'VpcId')

        if user_cidr:
            self.build_list_params(params, user_cidr, 'UserCidr')

        if vpc_name:
            self.build_list_params(params, vpc_name, 'VpcName')

        if description:
            self.build_list_params(params, description, 'Description')

        self.get_status('ModifyVpcAttribute', params)

        timeout = 16
        if str(wait).lower() in ['yes', 'true'] and wait_timeout:
            timeout = wait_timeout
        self.wait_for_vpc_status(vpc_id, 'Available', 4, timeout)

        return self.get_vpc_attribute(vpc_id)

    def delete_vpc(self, vpc_id):
        """
        Delete Vpc
        :type vpc_id: string
        :param vpc_id: Vpc Id of the targeted Vpc to terminate
        :rtype: bool
        :return: Return result of deleting.
       """
        changed = False

        params = {}

        self.build_list_params(params, vpc_id, 'VpcId')

        if self.wait_for_vpc_status(vpc_id, 'Available', 4, 16):
            changed = self.get_status('DeleteVpc', params)

        return changed

    def create_vswitch(self, zone_id, vpc_id, cidr_block, vswitch_name=None, description=None, client_token=None):
        """
        :type zone_id: String
        :param zone_id: Required parameter. ID of the zone to which an VSwitch belongs
        :type vpc_id: String
        :param vpc_id: Required parameter. The VPC ID of the new VSwitch
        :type cidr_block: String
        :param cidr_block: Required parameter. The cidr block representing the VSwitch, e.g. 10.0.0.0/8
        :type vswitch_name: String
        :param vswitch_name: A VSwitch name
        :type description: String
        :param description: Description about VSwitch
        
        :return: Return the operation result and details of created VSwitch
        """
        params = {}

        self.build_list_params(params, vpc_id, 'VpcId')
        self.build_list_params(params, zone_id, 'ZoneId')
        self.build_list_params(params, cidr_block, 'CidrBlock')

        if vswitch_name:
            self.build_list_params(params, vswitch_name, 'VSwitchName')

        if description:
                self.build_list_params(params, description, 'Description')

        if client_token:
            self.build_list_params(params, client_token, 'ClientToken')

        response = self.get_object('CreateVSwitch', params, ResultSet)
        vsw_id = str(response.vswitch_id)
        changed = self.wait_for_vswitch_status(vsw_id, 'Available', 4, 16)
        return changed, self.get_vswitch_attribute(vsw_id)

    def get_all_vswitches(self, vpc_id=None, vswitch_id=None, zone_id=None, is_default=None, pagenumber=1, pagesize=10):
        """
        Find Vpc
        :type vpc_id: String
        :param vpc_id: The VPC ID of the VSwitch
        :type vswitch_id: String
        :param vswitch_id: ID of the specified VSwitch
        :type zone_id: String
        :param zone_id: ID of the zone to which an VSwitch belongs
        :type is_default: bool
        :param is_default: The vswitch created by system if it is True
        :type pagenumber: integer
        :param pagenumber: Page number of the instance status list. The start value is 1. The default value is 1
        :type pagesize: integer
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50.
        The default value is 10
        :rtype: list
        :return: Return VSwitch list if VSwitches found along with VSwitch details.
        """
        params = {}

        if vpc_id:
            self.build_list_params(params, vpc_id, 'VpcId')

        if vswitch_id:
            self.build_list_params(params, vswitch_id, 'VSwitchId')

        if zone_id:
            self.build_list_params(params, zone_id, 'ZoneId')

        if is_default is not None:
            self.build_list_params(params, is_default, 'IsDefault')

        self.build_list_params(params, pagenumber, 'PageNumber')
        self.build_list_params(params, pagesize, 'PageSize')

        return self.get_list('DescribeVSwitches', params, ['VSwitches', VSwitch])

    def get_vswitch_attribute(self, vswitch_id):
        """
        method to get specified vswitch attribute 
        :return: Return vswitch with its attribute
        """

        response = self.get_all_vswitches(vswitch_id=vswitch_id)
        if response:
            return response[0]

        return None

    def modify_vswitch(self, vswitch_id, vswitch_name=None, description=None):
        """
        :type vswitch_id: String
        :param vswitch_id: Required parameter. The VSwitch ID.
        :type vswitch_name: String
        :param vswitch_name: A VSwitch name
        :type description: String
        :param description: Description about VSwitch
        
        :return: Return the operation result and details of modified VSwitch
        """
        params = {}

        self.build_list_params(params, vswitch_id, 'VSwitchId')

        if vswitch_name:
            self.build_list_params(params, vswitch_name, 'VSwitchName')

        if description:
            self.build_list_params(params, description, 'Description')

        self.get_status('ModifyVSwitchAttribute', params)
        self.wait_for_vswitch_status(vswitch_id, 'Available', 4, 16)
        return self.get_vswitch_attribute(vswitch_id)

    def delete_vswitch(self, vswitch_id):
        """
        Delete VSwitch
        :type vswitch_id : str
        :param vswitch_id: The Id of vswitch
        :rtype bool
        :return: return result of deleting
        """

        changed = False
        delay = 4
        timeout = 120

        params = {}

        self.build_list_params(params, vswitch_id, 'VSwitchId')

        if self.wait_for_vswitch_status(vswitch_id, 'Available', delay, timeout):
            while timeout > 0:
                try:
                    changed = self.get_status('DeleteVSwitch', params)
                    break
                except ServerException as e:
                    if e.error_code == DependencyViolation:
                        print "Specified vswitch %s has dependent resources - try again" % vswitch_id
                        timeout -= delay
                        if timeout <= 0:
                            raise Exception("Timeout Error: Waiting for deleting specified vswitch %s." % vswitch_id)

                        time.sleep(delay)

        return changed

    def delete_vswitch_with_vpc(self, vpc_id):
        """
        Delete VSwitches in the specified VPC
        :type vpc_id : str
        :param vpc_id: The Id of vpc to which vswitch belongs
        :rtype list
        :return: return list ID of deleted VSwitch
        """

        vswitch_ids = []
        if not vpc_id:
                raise Exception(msg="It must be specify vpc_id.")

        vswitches = self.get_all_vswitches(vpc_id=vpc_id)
        for vsw in vswitches:
            vsw_id = str(vsw.id)
            if self.delete_vswitch(vsw_id):
                vswitch_ids.append(vsw_id)

        return vswitch_ids

    def create_route_entry(self, route_table_id, destination_cidrblock, nexthop_type=None, nexthop_id=None, nexthop_list=None):
        """
        Create RouteEntry for VPC
        :type route_table_id: str
        :param route_table_id: ID of route table in the VPC
        :type destination_cidrblock: str
        :param destination_cidrblock: The destination CIDR of route entry. It must be a legal CIDR or IP address, such as: 192.168.0.0/24 or 192.168.0.1
        :type nexthop_type: str
        :param nexthop_type: The type of next hop. Available value options: Instance, Tunnel, HaVip, RouterInterface. Default is Instance.
        :type next_hop_id: str
        :param next_hop_id: The ID of next hop.
        :type nexthop_list: str
        :param nexthop_list: The route item of next hop list. 
        :rtype 
        :return Return result of Creating RouteEntry.
        """
        params = {}

        self.build_list_params(params, route_table_id, 'RouteTableId')
        self.build_list_params(params, destination_cidrblock, 'DestinationCidrBlock')

        if nexthop_type:
            self.build_list_params(params, nexthop_type, 'NextHopType')

        if nexthop_id:
            self.build_list_params(params, nexthop_id, 'NextHopId')

        if nexthop_list:
            self.build_list_params(params, nexthop_list, 'NextHopList')

        if self.get_status('CreateRouteEntry', params):
            return self.wait_for_route_entry_status(route_table_id, destination_cidrblock, 'Available', 4, 60)

        return None

    def get_route_entry_attribute(self, route_table_id, destination_cidrblock, nexthop_id=None):
        """
        Querying route entry attribute
        :type route_table_id: str
        :param route_table_id: ID of route table in the VPC
        :type destination_cidrblock: str
        :param destination_cidrblock: The destination CIDR of route entry. It must be a legal CIDR or IP address, such as: 192.168.0.0/24 or 192.168.0.1
        :type nexthop_id: str
        :param nexthop_type: The ID of next hop.
        :rtype 
        :return: VRouters in json format
        """

        route_entries = self.get_all_route_entries(route_table_id=route_table_id)
        if route_entries:
            for entry in route_entries:
                if destination_cidrblock == str(entry.destination_cidrblock):
                    return entry
        return None

    def get_all_route_entries(self, router_id=None, router_type=None, route_table_id=None, pagenumber=1, pagesize=10):
        """
        Querying all route entries in the specified router or route_tables_id
        :type router_id: str
        :param router_id: The ID of router which is to be fetched.
        :type router_type str
        :param router_type: The type of router which is to be fetched.
        :type route_table_id: str
        :param route_table_id: ID of route table in one VPC
        :type pagenumber: integer
        :param pagenumber: Page number of the route table list. The start value is 1. The default value is 1
        :type pagesize: integer
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50.
        The default value is 10 
        :rtype list<>
        :return: List of route entry.
        """
        route_tables = self.get_all_route_tables(router_id=router_id, router_type=router_type, route_table_id=route_table_id,
                                                 pagenumber=pagenumber, pagesize=pagesize)
        route_entries = []
        if route_tables:
            for table in route_tables:
                if table.route_entrys:
                    for entry in table.route_entrys['route_entry']:
                        route_entry = RouteEntry(self)
                        for k, v in entry.items():
                            setattr(route_entry, k, v)
                        route_entries.append(route_entry)

        return route_entries

    def delete_route_entry(self, route_table_id, destination_cidrblock=None, nexthop_id=None, nexthop_list=None):
        """
        Deletes the specified RouteEntry for the vpc
        :type route_table_id: str
        :param route_table_id: ID of route table in the VPC
        :type destination_cidrblock: str
        :param destination_cidrblock: The destination CIDR of route entry. It must be a legal CIDR or IP address, such as: 192.168.0.0/24 or 192.168.0.1
        :type next_hop_id: str
        :param next_hop_id: The ID of next hop.
        :type nexthop_list: str
        :param nexthop_list: The route item of next hop list.
        :rtype bool
        :return Return result of deleting route entry.
        """
        params = {}

        self.build_list_params(params, route_table_id, 'RouteTableId')
        if destination_cidrblock:
            self.build_list_params(params, destination_cidrblock, 'DestinationCidrBlock')

        if nexthop_id:
            self.build_list_params(params, nexthop_id, 'NextHopId')

        if nexthop_list:
            self.build_list_params(params, nexthop_list, 'NextHopList')

        return self.get_status('DeleteRouteEntry', params)

    def get_route_table_attribute(self, route_table_id):
        """
        Querying route table attribute
        :type route_table_id: str
        :param route_table_id: ID of route table in the VPC
        :rtype dict
        :return: VRouters in json format
        """
        return self.get_all_route_tables(route_table_id=route_table_id)

    def get_all_route_tables(self, router_id=None, router_type=None, route_table_id=None, pagenumber=1, pagesize=10):
        """
        Querying vrouter
        :type router_id: str
        :param router_id: The ID of router which is to be fetched.
        :type router_type str
        :param router_type: The type of router which is to be fetched.
        :type route_table_id: str
        :param route_table_id: ID of route table in one VPC
        :type pagenumber: integer
        :param pagenumber: Page number of the route entry list. The start value is 1. The default value is 1
        :type pagesize: integer
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50.
        The default value is 10 
        :rtype list<>
        :return: List of route entry.
        """
        params = {}

        if router_id:
            self.build_list_params(params, router_id, 'RouterId')

        if router_type:
            self.build_list_params(params, router_type, 'RouterType')

        if route_table_id:
            self.build_list_params(params, route_table_id, 'RouteTableId')

        if pagenumber:
            self.build_list_params(params, pagenumber, 'PageNumber')

        if pagesize:
            self.build_list_params(params, pagesize, 'PageSize')

        return self.get_list('DescribeRouteTables', params, ['RouteTables', RouteTable])

    def get_instance_info(self):
        """
        method to get all Instances of particular region 
        :return: Return All Instances in the region
        """
        params = {}
        results = []

        try:
            v_ids = {}
            response = self.get_status('DescribeInstances', params)
            results.append(response)
            
        except Exception as ex:        
            error_code = ex.error_code
            error_msg = ex.message
            results.append({"Error Code": error_code, "Error Message": error_msg})

        return results

    def allocate_eip_address(self, bandwidth=5, internet_charge_type='PayByBandwidth', client_token=None):
        """
        method to query eip addresses in the region
        :type int
        :param bandwidth : bandwidth of the eip address. Default to 5
        :type internet_charge_type : str
        :param internet_charge_type : paybytraffic or paybybandwidth types
        :return: Return the allocationId , requestId and EIP address
        """
        params = {}
        self.build_list_params(params, str(bandwidth), 'Bandwidth')
        self.build_list_params(params, internet_charge_type, 'InternetChargeType')
        if client_token:
            self.build_list_params(params, client_token, 'ClientToken')
                  
        result = self.get_object('AllocateEipAddress', params, ResultSet)
        if result:
            return self.wait_for_eip_status(allocation_id=result.allocation_id, eip_address=result.eip_address,
                                            status='Available', interval=3, timeout=60)

        return None

    def get_all_eip_addresses(self, status=None, ip_address=None, allocation_id=None, associated_instance_type=None,
                              associated_instance_id=None, page_number=1, page_size=50):
        """
        Get EIP details for a region
        :param status: The EIP status includes Associating | Unassociating | InUse | Available
        :param ip_address: The EIP ip address
        :param allocation_id: ID of the allocated EIP
        :param associated_instance_type: The type of the associate device
        :param associated_instance_id: The ID of the associate device
        :param pagenumber: Page number. The start value is 1. The default value is 1
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50. Default to 50.
        :return:
        """
        params = {}

        if status:
            self.build_list_params(params, status, 'Status')
        if ip_address:
            self.build_list_params(params, ip_address, 'EipAddress')
        if allocation_id:
            self.build_list_params(params, allocation_id, 'AllocationId')
        if associated_instance_type:
            self.build_list_params(params, associated_instance_type, 'AssociatedInstanceType')
        if associated_instance_id:
            self.build_list_params(params, associated_instance_id, 'AssociatedInstanceId')

        self.build_list_params(params, page_number, 'PageNumber')
        self.build_list_params(params, page_size, 'PageSize')

        return self.get_list('DescribeEipAddresses', params, ['EipAddresses', Eip])

    def associate_eip(self, allocation_id, instance_id):
        """
        :type allocation_id:string
        :param allocation_id:The instance ID of the EIP
        :type instance_id:string
        :param instance_id:The ID of an ECS instance
        :param client_token: Used to ensure the idempotence of the request
        :return:Returns the status of operation
        """
        params = {}

        self.build_list_params(params, allocation_id, 'AllocationId')
        self.build_list_params(params, instance_id, 'InstanceId')
        if str(instance_id).startswith("lb-"):
            self.build_list_params(params, 'SlbInstance', 'InstanceType')
       
        self.get_status('AssociateEipAddress', params)
        return self.wait_for_eip_status(allocation_id=allocation_id, status="InUse", interval=2, timeout=60) is None

    def disassociate_eip(self, allocation_id, instance_id):
        """
        :type allocation_id:string
        :param allocation_id:The instance ID of the EIP
        :type instance_id:string
        :param instance_id:The ID of an ECS instance
        :return:Request Id
        """
        params = {}
        self.build_list_params(params, allocation_id, 'AllocationId')
        self.build_list_params(params, instance_id, 'InstanceId')
        self.get_status('UnassociateEipAddress', params)

        return self.wait_for_eip_status(allocation_id=allocation_id, status="Available", interval=2, timeout=60) is None

    def modify_eip(self, allocation_id, bandwidth):
        """
        :type allocation_id:string
        :param allocation_id:The instance ID of the EIP
        :type bandwidth:int
        :param bandwidth:Bandwidth of the EIP instance
        :return:Request Id
        """
        params = {}

        self.build_list_params(params, allocation_id, 'AllocationId')
        if int(bandwidth) > 0:
            self.build_list_params(params, int(bandwidth), 'Bandwidth')
        return self.get_status('ModifyEipAddressAttribute', params)

    def release_eip(self, allocation_id):
        """
        To release Elastic Ip
        :type allocation_id: string
        :param allocation_id: To release the allocation ID,allocation ID uniquely identifies the EIP
        :return: Return status of operation
        """
        params = {}

        self.build_list_params(params, allocation_id, 'AllocationId')
        try_times = 10
        while try_times > 0:
            self.get_status('ReleaseEipAddress', params)
            eips = self.get_all_eip_addresses(allocation_id=allocation_id)
            if not eips or len(eips) < 1:
                return True
            time.sleep(3)
            try_times -= 1

        raise Exception("Retry 10 times to release EIP failed."
                        "Please ensure EIP status is Available before releasing it.")

    def get_all_vrouters(self, vrouter_id=None, pagenumber=None, pagesize=None):
        """
        Querying vrouter
        :param vrouter_id: VRouter_Id to be fetched
        :type vrouter_id: str
        :type pagenumber: integer
        :param pagenumber: Page number of the instance status list. The start value is 1. The default value is 1
        :type pagesize: integer
        :param pagesize: Sets the number of lines per page for queries per page. The maximum value is 50.
        The default value is 10
        :return: VRouters in json format
        """
        params = {}
        results = []

        try:
            if vrouter_id is not None :
                self.build_list_params(params, vrouter_id, 'VRouterId')

            if pagenumber is not None :
                self.build_list_params(params, pagenumber, 'PageNumber')

            if pagesize is not None :
                self.build_list_params(params, pagesize, 'PageSize')

            results = self.get_status('DescribeVRouters', params)
        except Exception as ex:
            error_code = ex.error_code
            error_msg = ex.message
            results.append({"Error Code": error_code, "Error Message": error_msg})

        return False, results

    def wait_for_eip_status(self, allocation_id, status, eip_address=None, interval=DefaultWaitForInterval, timeout=DefaultTimeOut):
        """
        wait for bind ok
        :param eip_address:
        :param allocation_id:
        :param status:
        :return: 
        """
        try:
            tm = 0
            while tm < timeout:
                eips = self.get_all_eip_addresses(allocation_id=allocation_id, ip_address=eip_address)
                if not eips or len(eips) < 1:
                    return None
                if str.lower(status) == str.lower(eips[0].status):
                    return eips[0]
                tm += interval
                if tm >= timeout:
                    raise Exception("Timeout Error: Waiting For EIP Status {0}, time-consuming {1} seconds.".format(status, timeout))
                time.sleep(interval)
            return None
        except Exception as e:
            raise Exception("Waiting For EIP Status {0} Error: {1}.".format(status, e))

    def get_vswitch_status(self, vpc_id, zone_id=None, vswitch_id=None, pagenumber=None, pagesize=None):
        """
        List VSwitches of VPC with their status
        :type vpc_id: string
        :param vpc_id: ID of Vpc from which VSwitch belongs
        :type zone_id: string
        :param zone_id: ID of the Zone
        :type vswitch_id: string
        :param vswitch_id: The ID of the VSwitch to be queried
        :type pagenumber: integer
        :param pagenumber: Page number of the instance status list. The start value is 1. The default value is 1
        :type pagesize: integer
        :param pagesize: The number of lines per page set for paging query. The maximum value is 50 and default
        value is 10
        :return: Returns list of vswitches in VPC with their status
        """
        params = {}
        results = []

        self.build_list_params(params, vpc_id, 'VpcId')
        if zone_id:
            self.build_list_params(params, zone_id, 'ZoneId')
        if vswitch_id:
            self.build_list_params(params, vswitch_id, 'VSwitchId')
        if pagenumber:
            self.build_list_params(params, pagenumber, 'PageNumber')
        if pagesize:
            self.build_list_params(params, pagesize, 'PageSize')

        try:
            results = self.get_status('DescribeVSwitches', params)
        except Exception as ex:
            error_code = ex.error_code
            error_msg = ex.message
            results.append({"Error Code": error_code, "Error Message": error_msg})

        return False, results

    def wait_for_vpc_status(self, vpc_id, status, delay=DefaultWaitForInterval, timeout=DefaultTimeOut):

        try:
            while True:
                vpc = self.get_vpc_attribute(vpc_id)
                if vpc and str(vpc.status) in [status, str(status).lower()]:
                    return True

                timeout -= delay

                if timeout <= 0:
                    raise Exception("Timeout Error: Waiting for VPC status is %s, time-consuming %d seconds." % (status, timeout))

                time.sleep(delay)
        except Exception as e:
            raise e

    def wait_for_vswitch_status(self, vswitch_id, status, delay=DefaultWaitForInterval, timeout=DefaultTimeOut):
        try:
            while True:
                vsw = self.get_vswitch_attribute(vswitch_id)
                if vsw and str(vsw.status) in [status, str(status).lower()]:
                    return True

                timeout -= delay

                if timeout <= 0:
                    raise Exception("Timeout Error: Waiting for VSwitch status is %s, time-consuming %d seconds." % (status, timeout))

                time.sleep(delay)
        except Exception as e:
            raise e

    def wait_for_route_entry_status(self, route_table_id, destination_cidrblock, status, delay=DefaultWaitForInterval, timeout=DefaultTimeOut):
        try:
            tm = 0
            while tm < timeout:
                route_entry = self.get_route_entry_attribute(route_table_id, destination_cidrblock)
                if route_entry and str.lower(route_entry.status) == str.lower(status):
                    return route_entry

                tm += delay

                if tm >= timeout:
                    raise Exception("Timeout Error: Waiting for route entry status is %s, time-consuming %d seconds." % (status, timeout))

                time.sleep(delay)
            return None
        except Exception as e:
            raise Exception("Waiting For route entry Status {0} Error: {1}.".format(status, e))
