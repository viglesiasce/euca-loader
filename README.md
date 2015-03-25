euca-loader
===========
Load Testing Framework for Eucalyptus

Requirements
==================
- Cloudformation enabled cloud
- Ubuntu Trusty Image

How To
==================
- Create the stack by (minimally) passing in your ImageID, KeyName, and CredentialURL (this URL must be accessible by your instances in the cloud and contain the test account credentials)

```./create-locust-cfn-template.py > locustio.cfn; euform-create-stack --template-file locustio.cfn my-stack-name -p ImageID=emi-F6144478 -p KeyName=vic -p CredentialURL='http://10.111.1.5:8773/services/objectstorage/creds/admin.zip'```

- Check that the stack is complete by doing ```euform-describe-stacks```
- The system is now bootstrapping
- In the describe-stacks output you will see a line with the WebPortalUrl, this is where you can start your load test.
- Once at the web portal make sure that the slave count in the top right reaches at least 1
- Enter the number of total concurrent users youd like to simulate and how quickly youd like them to spawn, then hit the "Start swarming" button
- Locust will then show you the results of your requests. In order to see real time graphs of operation timings, run  ```euform-describe-stacks``` and point your browser to the GrafanaURL

Logging
===================
- Logs for both the master and slave Locust processes can be found at /mnt/locust.log. 
- Logs for influxdb are in /opt/influxdb/shared/log.txt
