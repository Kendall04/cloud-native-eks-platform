import boto3
import os

ec2 = boto3.client('ec2')

# Environment variables provided by Terraform
SUBNET_A_ID = os.environ.get('SUBNET_A_ID')
SUBNET_B_ID = os.environ.get('SUBNET_B_ID')
EIP_A_ALLOCATION_ID = os.environ.get('EIP_A_ALLOCATION_ID')
EIP_B_ALLOCATION_ID = os.environ.get('EIP_B_ALLOCATION_ID')


def lambda_handler(event, context):
    detail = event.get('detail', {})
    instance_id = detail.get('instance-id')
    state = detail.get('state')

    # Only act when the instance enters the "running" state
    if not instance_id or state != 'running':
        print(f"Ignoring event: instance_id={instance_id}, state={state}")
        return

    print(f"Assigning EIP to NAT instance: {instance_id}")

    # Retrieve instance information
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    instance = resp['Reservations'][0]['Instances'][0]

    subnet_id = instance.get('SubnetId')
    eni_id = instance['NetworkInterfaces'][0]['NetworkInterfaceId']

    # Choose the correct EIP based on the subnet (AZ)
    if subnet_id == SUBNET_A_ID:
        allocation_id = EIP_A_ALLOCATION_ID
    elif subnet_id == SUBNET_B_ID:
        allocation_id = EIP_B_ALLOCATION_ID
    else:
        print(f"Subnet {subnet_id} does not match A/B, skipping.")
        return

    print(f"Associating EIP {allocation_id} to ENI {eni_id}")

    ec2.associate_address(
        AllocationId=allocation_id,
        NetworkInterfaceId=eni_id,
        AllowReassociation=True
    )

    print("EIP successfully associated.")
