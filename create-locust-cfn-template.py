#!/usr/bin/python
from troposphere import FindInMap, Base64, Output, GetAtt
from troposphere import Parameter, Ref, Template, Join
from troposphere.cloudformation import WaitCondition, WaitConditionHandle
import troposphere.ec2 as ec2
import troposphere.autoscaling as autoscaling


template = Template()
image_id = template.add_parameter(Parameter(
    "ImageID",
    Description="Image ID to run instance with",
    Type="String"
))
instance_type = template.add_parameter(Parameter(
    "InstanceType",
    Description="Instance type for instances",
    Default="m1.large",
    Type="String"
))
keyname_param = template.add_parameter(Parameter(
    "KeyName",
    Description="Name of an existing EC2 KeyPair to enable SSH "
                "access to the instance",
    Type="String"
))
script_url = template.add_parameter(Parameter(
    "ScriptURL",
    Description="URL used to download the locustfile",
    Type="String",
    Default="https://raw.githubusercontent.com/viglesiasce/euca-loader/master/locustfile.py"
))
desired_capacity = template.add_parameter(Parameter(
    "DesiredCapacity",
    Description="Desired starting capacity for slaves",
    Type="Number",
    MaxValue="5",
    Default="1",
    MinValue="1",
))
creds_url = template.add_parameter(Parameter(
    "CredentialURL",
    Description="URL used to download the eucalyptus credentials",
    Type="String"
))
eutester_branch = template.add_parameter(Parameter(
    "EutesterBranch",
    Description="Eutester branch to install",
    Type="String",
    Default="maint-4.1"
))
eutester_repo = template.add_parameter(Parameter(
    "EutesterRepo",
    Description="Eutester repo to download from",
    Type="String",
    Default="https://github.com/eucalyptus/eutester"
))
default_dashboard = template.add_parameter(Parameter(
    "DefaultDashboard",
    Description="Default dashboard to bring up in Grafana",
    Type="String",
    Default="https://raw.githubusercontent.com/viglesiasce/euca-loader/master/grafana-dashboard.json"
))
grafana_config = template.add_parameter(Parameter(
    "GrafanaConfig",
    Description="Grafana config.json URL",
    Type="String",
    Default="https://raw.githubusercontent.com/viglesiasce/euca-loader/master/grafana-config.js"
))

master_handle = template.add_resource(WaitConditionHandle("MasterHandle"))
master_complete_condition = template.add_resource(
    WaitCondition(
        "MasterComplete",
        Handle=Ref(master_handle),
        Timeout="2400"
    )
)

slave_handle = template.add_resource(WaitConditionHandle("SlaveHandle"))
slave_complete_condition = template.add_resource(
    WaitCondition(
        "SlaveComplete",
        Handle=Ref(slave_handle),
        Timeout="2400",
        Count=Ref(desired_capacity)
    )
)

shared_userdata = Join("", ["""#!/bin/bash -xe
INSTANCE_ID=`curl http://169.254.169.254/latest/meta-data/instance-id`
cat > /tmp/instance-handle-data <<EOF
{
 "Status" : "SUCCESS",
 "Reason" : "Configuration Complete",
 "UniqueId" : "$INSTANCE_ID",
 "Data" : "Application has completed configuration."
}
EOF
LOG_FILE=/mnt/locust.log
apt-get install -y python-setuptools python-dev git python-pip gcc unzip ntp apache2
ntpdate -u pool.ntp.org
easy_install locustio
easy_install influxdb
pushd /root
rm -rf eutester
git clone """, Ref(eutester_repo), """ -b """, Ref(eutester_branch), """
pushd eutester
git pull
python setup.py install
popd
curl """, Ref(script_url), """ > locustfile.py
rm -rf creds
mkdir -p creds
pushd creds
curl """, Ref(creds_url), """ > admin.zip
unzip -o admin.zip
popd
"""])

master_userdata = Join("", [shared_userdata,
'''
wget http://get.influxdb.org/influxdb_0.8.8_amd64.deb
dpkg -i influxdb_0.8.8_amd64.deb
GRAFANA_VERSION=1.9.1
wget http://grafanarel.s3.amazonaws.com/grafana-$GRAFANA_VERSION.zip
unzip grafana-$GRAFANA_VERSION.zip
cp -a grafana-$GRAFANA_VERSION/* /var/www/html/
curl ''', Ref(grafana_config), ''' > /var/www/html/config.js
pub_ip=`curl http://169.254.169.254/latest/meta-data/public-ipv4`
sed -i "s/localhost/$pub_ip/g"  /var/www/html/config.js
curl ''', Ref(default_dashboard), ''' >  /var/www/html/app/dashboards/locust.json
service apache2 start
nohup /usr/bin/influxdb -pidfile /opt/influxdb/shared/influxdb.pid -config /opt/influxdb/shared/config.toml &
sleep 30
cat > setup_influxdb.py <<EOF
from influxdb.influxdb08 import InfluxDBClient
db = InfluxDBClient()
db.create_database('locust')
db.create_database('grafana')
db.add_cluster_admin('admin','admin')
EOF
python setup_influxdb.py
locust --master --logfile=$LOG_FILE &
curl -T /tmp/instance-handle-data "''', Ref(master_handle)  ,'''"'''])

instance_sg = template.add_resource(
        ec2.SecurityGroup(
            "LocustSecurityGroup",
            GroupDescription="Enable Locust and Grafana access on the inbound port",
            SecurityGroupIngress=[
                ec2.SecurityGroupRule(
                    IpProtocol="tcp",
                    FromPort="8083",
                    ToPort="8089",
                    CidrIp="0.0.0.0/0",
                ),
                ec2.SecurityGroupRule(
                    IpProtocol="tcp",
                    FromPort="80",
                    ToPort="80",
                    CidrIp="0.0.0.0/0",
                ),
                ec2.SecurityGroupRule(
                    IpProtocol="tcp",
                    FromPort="22",
                    ToPort="22",
                    CidrIp="0.0.0.0/0",
                )
            ]
        )
    )

master = template.add_resource(ec2.Instance(
    "LocustMaster",
    ImageId=Ref(image_id),
    InstanceType=Ref(instance_type),
    KeyName=Ref(keyname_param),
    SecurityGroups=[Ref(instance_sg)],
    UserData=Base64(master_userdata),
    Tags=[ec2.Tag("Name", "Locust Master")]
))

slave_userdata = Base64(Join("", [shared_userdata,
'''sleep 20;
export MASTER_IP=''', GetAtt(master, "PublicIp"), '''
locust --slave --master-host=$MASTER_IP --logfile=$LOG_FILE &
curl -T /tmp/instance-handle-data "''', Ref(slave_handle)  ,'''"''']))
slave_lc  = template.add_resource(autoscaling.LaunchConfiguration("LocustSlave",
                                                                  ImageId=Ref(image_id),
                                                                  InstanceType=Ref(instance_type),
                                                                  UserData=slave_userdata,
                                                                  KeyName=Ref(keyname_param), 
                                                                  SecurityGroups=[Ref(instance_sg)]))

slave_asg = template.add_resource(autoscaling.AutoScalingGroup("LocustSlaveASG", AvailabilityZones=[GetAtt(master, "AvailabilityZone")],
                                                               LaunchConfigurationName=Ref(slave_lc), MaxSize="5",
                                                               Tags=[
                                                                       autoscaling.Tag("Name", "Locust Slave", True)
                                                                   ],
                                                               DesiredCapacity=Ref(desired_capacity),
                                                               MinSize="1"))

template.add_output(Output(
    "WebPortalUrl",
    Description="Web address for Locust Master",
    Value=Join("", ["Login here to start your test: http://", GetAtt(master, "PublicDnsName"), ":8089"])
))
template.add_output(Output(
    "ScriptURL",
    Description="Web location of LocustIO script being excecuted",
    Value=Join("", ["Currently executing the following script: ", Ref(script_url)])
))
template.add_output(Output(
    "GrafanaURL",
    Description="Web address for Real Time Graphs",
    Value=Join("", ["Login here for real time graphs: http://", GetAtt(master, "PublicDnsName")])
))

print(template.to_json())
