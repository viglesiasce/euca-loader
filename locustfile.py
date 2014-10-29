# Software License Agreement (BSD License)
#
# Copyright (c) 2009-2011, Eucalyptus Systems, Inc.
# All rights reserved.
#
# Redistribution and use of this software in source and binary forms, with or
# without modification, are permitted provided that the following conditions
# are met:
#
#   Redistributions of source code must retain the above
#   copyright notice, this list of conditions and the
#   following disclaimer.
#
#   Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the
#   following disclaimer in the documentation and/or other
#   materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: Vic Iglesias vic.iglesias@eucalyptus.com
#
import os
import time
from eucaops import Eucaops
from locust import Locust, events, web, TaskSet, task
from influxdb import client as influxdb

class EucaopsClient(Eucaops):
    def __init__(self, *args, **kwargs):
        """
        This class extends Eucaops in order to provide a feedback
        loop to LocustIO. It generates a Eucaops client and fires events
        to the LocustIO when the time_operation wrapper is called with a method
        as its arguments.

        :param args: positional args passed to Eucaops constructor
        :param kwargs: keyword args passed to Eucaops constructor
        """
        super(EucaopsClient, self).__init__(*args, **kwargs)
        self.db = influxdb.InfluxDBClient(os.getenv('MASTER_IP', 'localhost'), 8086, 'admin', 'admin', 'locust')

    def time_operation(self, method, *args, **kwargs):
        start_time = time.time()
        method_name = method.__name__
        try:
            result = method(*args, **kwargs)
        except Exception as e:
            current_time = time.time()
            total_time = int((current_time - start_time) * 1000)
            events.request_failure.fire(request_type="eutester",
                                        name=method_name,
                                        response_time=total_time, exception=e)
            data = [{"points": [[total_time, 0]],
                     "name": method_name,
                     "columns":["total_time", "length"]}]
            self.db.write_points(data)
        else:
            current_time = time.time()
            total_time = int((current_time - start_time) * 1000)
            try:
                length = len(result)
            except:
                length = 0
            events.request_success.fire(request_type="eutester",
                                        name=method_name,
                                        response_time=total_time,
                                        response_length=length)
            data = [{"points": [[total_time, length]],
                     "name": method_name,
                     "columns":["total_time", "length"]}]
            self.db.write_points(data)
            return result


class EucaopsLocust(Locust):
    def __init__(self):
        super(EucaopsLocust, self).__init__()
        self.client = EucaopsClient(credpath="creds")

class EC2Read(TaskSet):
    @task(10)
    def get_instances(self):
        self.client.time_operation(self.client.get_instances)

    @task(10)
    def get_volumes(self):
        self.client.time_operation(self.client.get_volumes)


class EC2Create(TaskSet):

    @task(1)
    def run_instances(self):
        reservation = self.client.time_operation(self.client.run_instance)
        self.client.time_operation(self.client.terminate_instances, reservation)

    @task(1)
    def create_volumes(self):
        volumes = self.client.time_operation(self.client.create_volumes,
                                             zone="one")
        self.client.time_operation(self.client.delete_volumes, volumes)

    @task(1)
    def allocate_address(self):
        address = self.client.time_operation(self.client.allocate_address)
        self.client.time_operation(self.client.release_address, address)


class S3Operations(TaskSet):
    @task(10)
    def list_buckets(self):
        self.client.time_operation(self.client.s3.get_all_buckets)

    @task(1)
    def create_bucket(self):
        bucket = self.client.time_operation(self.client.s3.create_bucket,
                                            str(int(time.time())).
                                            lower())
        if bucket:
            self.client.time_operation(self.client.s3.delete_bucket, bucket)

class AverageUser(EC2Create, EC2Read, S3Operations):
    pass

class EucaopsUser(EucaopsLocust):
    min_wait = 1
    max_wait = 1
    task_set = EC2Read

    def on_start(self):
        pass

    def on_stop(self):
        self.client.cleanup_resources()

