#!/usr/bin/python
from troposphere import FindInMap, Base64, Output, GetAtt
from troposphere import Parameter, Ref, Template, Join
import troposphere.ec2 as ec2
import troposphere.autoscaling as autoscaling


template = Template()
image_id = template.add_parameter(Parameter(
    "ImageID",
    Description="Image ID to run instance with",
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
    Default="testing"
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

shared_userdata = Join("", ["""#!/bin/bash
LOG_FILE=/mnt/locust.log
mkfs.ext4 -F /dev/vdb
mount /dev/vdb /mnt/
yum install -y python-setuptools python-devel python-pip git gcc unzip ntp gcc-c++
ntpdate -u pool.ntp.org
pip install locustio
pip install pyzmq
pip install influxdb
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
yum install -y http://s3.amazonaws.com/influxdb/influxdb-latest-1.x86_64.rpm
yum install -y wget httpd unzip
wget http://grafanarel.s3.amazonaws.com/grafana-1.8.1.zip
unzip grafana-1.8.1.zip
cp -a grafana-1.8.1/* /var/www/html/
curl ''', Ref(grafana_config), ''' > /var/www/html/config.js
pub_ip=`curl http://169.254.169.254/latest/meta-data/public-ipv4`
sed -i "s/localhost/$pub_ip/g"  /var/www/html/config.js
curl ''', Ref(default_dashboard), ''' >  /var/www/html/app/dashboards/locust.json
service httpd start
nohup /usr/bin/influxdb -pidfile /opt/influxdb/shared/influxdb.pid -config /opt/influxdb/shared/config.toml &
chkconfig influxdb on
sleep 30
cat > setup_influxdb.py <<EOF
from influxdb import client as influxdb
db = influxdb.InfluxDBClient()
db.create_database('locust')
db.create_database('grafana')
db.add_cluster_admin('admin','admin')
EOF
python setup_influxdb.py
locust --master --logfile=$LOG_FILE
'''])
master = template.add_resource(ec2.Instance(
    "LocustMaster",
    ImageId=Ref(image_id),
    InstanceType="m1.small",
    KeyName=Ref(keyname_param),
    SecurityGroups=["default"],
    UserData=Base64(master_userdata)
))

slave_userdata = Base64(Join("", [shared_userdata,
"""sleep 20;
export MASTER_IP=""", GetAtt(master, "PublicIp"), """
locust --slave --master-host=$MASTER_IP --logfile=$LOG_FILE
"""]))

slave_lc  = template.add_resource(autoscaling.LaunchConfiguration("LocustSlave",
                                                                  ImageId=Ref(image_id),
                                                                  InstanceType="m1.small",
                                                                  UserData=slave_userdata,
                                                                  KeyName=Ref(keyname_param)))

slave_asg = template.add_resource(autoscaling.AutoScalingGroup("LocustSlaveASG", AvailabilityZones=[GetAtt(master, "AvailabilityZone")],
                                                               LaunchConfigurationName=Ref(slave_lc), MaxSize="5",
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
