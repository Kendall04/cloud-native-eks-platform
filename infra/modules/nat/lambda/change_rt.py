import boto3
import os
from botocore.exceptions import ClientError

ec2 = boto3.client('ec2')

# Environment variables provided by Terraform
ROUTE_TABLE_A_ID = os.environ.get('ROUTE_TABLE_A_ID')
ROUTE_TABLE_B_ID = os.environ.get('ROUTE_TABLE_B_ID')
SUBNET_A_ID = os.environ.get('SUBNET_A_ID')
SUBNET_B_ID = os.environ.get('SUBNET_B_ID')


def lambda_handler(event, context):
    detail = event.get('detail', {})
    instance_id = detail.get('instance-id')
    state = detail.get('state')

    # Only process events when the instance enters the "running" state
    if not instance_id or state != 'running':
        print(f"Ignoring event: instance_id={instance_id}, state={state}")
        return

    print(f"Processing new NAT instance: {instance_id}")

    # Fetch instance metadata
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    instance = resp['Reservations'][0]['Instances'][0]

    subnet_id = instance.get('SubnetId')
    eni_id = instance['NetworkInterfaces'][0]['NetworkInterfaceId']

    # Determine which route table to update based on subnet
    if subnet_id == SUBNET_A_ID:
        route_table_id = ROUTE_TABLE_A_ID
    elif subnet_id == SUBNET_B_ID:
        route_table_id = ROUTE_TABLE_B_ID
    else:
        print(f"Subnet {subnet_id} does not match configured subnets, skipping.")
        return

    print(f"Updating default route in {route_table_id} → ENI {eni_id}")

    try:
        # Replace route if it already exists
        ec2.replace_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock='0.0.0.0/0',
            NetworkInterfaceId=eni_id
        )
        print("Route successfully replaced.")

    except ClientError as e:
        # If route does not exist, create it
        if "InvalidParameterValue" in str(e):
            print("Route did not exist. Creating it now...")
            ec2.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock='0.0.0.0/0',
                NetworkInterfaceId=eni_id
            )
            print("Route successfully created.")
        else:
            print(f"Unexpected error: {e}")
            raise
