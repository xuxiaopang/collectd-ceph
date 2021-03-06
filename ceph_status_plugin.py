#!/usr/bin/env python
#
# vim: tabstop=4 shiftwidth=4

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; only version 2 of the License is applicable.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# Authors:
#   Ricardo Rocha <ricardo@catalyst.net.nz>
#
# About this plugin:
#   This plugin collects information regarding Ceph pools.
#
# collectd:
#   http://collectd.org
# collectd-python:
#   http://collectd.org/documentation/manpages/collectd-python.5.shtml
# ceph pools:
#   http://ceph.com/docs/master/rados/operations/pools/
#

import collectd
import json
import traceback

import base

class CephStatusPlugin(base.Base):

    def __init__(self):
        base.Base.__init__(self)
        self.prefix = 'status'

    def get_stats(self):
        """Retrieves stats from ceph pools"""

        #ceph_cluster = "." % (self.prefix, self.cluster)
        #ceph_cluster = ".status"
        #data = { ceph_cluster: {} }
	ceph_cluster = "."
        data = {
            ceph_cluster: {
                'status':{},
                'pools' :{},
                'df': {},
                },
        }

        stats_output = None
        try:
            stats_output = self.exec_cmd('status')
            pools_output = self.exec_cmd('osd pool stats')
            df_output = self.exec_cmd('df')
        except Exception as exc:
            collectd.error("ceph-status: failed to ceph status :: %s :: %s"
                    % (exc, traceback.format_exc()))
            return
######### parse `ceph -s`
        json_status_data = json.loads(stats_output)
    	data[ceph_cluster]['status'] = {}
# read write speed of cluster
    	pgmap = json_status_data['pgmap']
    	for stat  in ('num_pgs','data_bytes','bytes_used','bytes_avail','bytes_total', 'recovering_bytes_per_sec', 
            'read_bytes_sec', 'write_bytes_sec', 'read_op_per_sec','write_op_per_sec', 'op_per_sec','misplaced_ratio','degraded_ratio'):
    	    data[ceph_cluster]['status'][stat] = pgmap[stat] if pgmap.has_key(stat) else 0
# looking for slow request
        summary = json_status_data['health']['summary']
	data[ceph_cluster]['status']['slow_requests'] = 0
        for stat in summary:
            if stat['summary'].split(" ")[1] == 'requests':
                data[ceph_cluster]['status']['slow_requests'] = stat['summary'].split(" ")[0]
# osd up/in/down status                
        osdmap = json_status_data['osdmap']['osdmap']
        for stat in ('num_osds', 'num_up_osds', 'num_in_osds'):
            data[ceph_cluster]['status'][stat] = osdmap[stat] if osdmap.has_key(stat) else 0
        data[ceph_cluster]['status']['num_down_osds'] =  data[ceph_cluster]['status']['num_osds'] - data[ceph_cluster]['status']['num_up_osds']
# cluster status : OK/WARN/ERROR
        status = json_status_data['health']['overall_status']
        if status == "HEALTH_OK":
            data[ceph_cluster]['status']['overall_status'] = 0
        if status == "HEALTH_WARN":
            data[ceph_cluster]['status']['overall_status'] = 1
        if status == "HEALTH_ERR":
            data[ceph_cluster]['status']['overall_status'] = 2

######## parse `ceph osd pool stats`
        json_pools_data = json.loads(pools_output)
        data[ceph_cluster]['pools'] = {}

        for pool in json_pools_data:
            pool_name = pool['pool_name']+"."
            data[ceph_cluster]['pools'][pool_name] = {}
            pool_data = data[ceph_cluster]['pools'][pool_name]
            for stat in ('read_bytes_sec', 'write_bytes_sec', 'op_per_sec', 'write_op_per_sec', 'read_op_per_sec'):
                pool_data[stat] = pool['client_io_rate'][stat] if pool['client_io_rate'].has_key(stat) else 0
            for recover_stat in ('recovering_objects_per_sec', 'recovering_bytes_per_sec'):
                pool_data[recover_stat] = pool['recovery_rate'][recover_stat] if pool['recovery_rate'].has_key(recover_stat) else 0

######## parse `ceph df`        
        json_df_data = json.loads(df_output)
        data[ceph_cluster]['df'] = {}
        for pool in json_df_data['pools']:
            pool_name = pool['name']+"."
            pool_data = data[ceph_cluster]["pools"][pool_name]
            for stat in ('bytes_used', 'kb_used', 'objects', 'max_avail'):
                pool_data[stat] = pool['stats'][stat] if pool['stats'].has_key(stat) else 0
        return data
'''
        # push totals from df
        if json_df_data['stats'].has_key('total_bytes'):
            # ceph 0.84+
            data[ceph_cluster]['status']['total_space'] = int(json_df_data['stats']['total_bytes'])
            data[ceph_cluster]['status']['total_used'] = int(json_df_data['stats']['total_used_bytes'])
            data[ceph_cluster]['status']['total_avail'] = int(json_df_data['stats']['total_avail_bytes'])
'''
try:
    plugin = CephStatusPlugin()
except Exception as exc:
    collectd.error("ceph-status: failed to initialize ceph status plugin :: %s :: %s"
            % (exc, traceback.format_exc()))

def configure_callback(conf):
    """Received configuration information"""
    plugin.config_callback(conf)
    collectd.register_read(read_callback, plugin.interval)

def read_callback():
    """Callback triggerred by collectd on read"""
    plugin.read_callback()

collectd.register_init(CephStatusPlugin.reset_sigchld)
collectd.register_config(configure_callback)
