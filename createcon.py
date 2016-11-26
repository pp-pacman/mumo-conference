#!/usr/bin/env python
# -*- coding: utf-8

# Copyright (C) 2016 Frank Fitzke <ffitzke@piratenpartei-nrw.de>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:

# - Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# - Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# - Neither the name of the Mumble Developers nor the names of its
#   contributors may be used to endorse or promote products derived from this
#   software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# `AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE FOUNDATION OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

#
# createcon.py
# This module creates differents profile of conferencerooms
# Not for Multiserver yet


from mumo_module import (commaSeperatedIntegers,
                         MumoModule)
from datetime import datetime, date, time

import sched, time

import thread
import threading
from threading import Timer

import json


class Operation(threading._Timer):
   def __init__(self, *args, **kwargs):
      threading._Timer.__init__(self, *args, **kwargs)
      self.setDaemon(True)

   def run(self):
      while True:
         self.finished.clear()
         self.finished.wait(self.interval)
         if not self.finished.isSet():
            self.function(*self.args, **self.kwargs)
         else:
            return
         self.finished.set()


class Manager(object):
   ops = []
   def add_operation(self, operation, interval, args=[], kwargs={}):
      op = Operation(interval, operation, args, kwargs)
      self.ops.append(op)
      thread.start_new_thread(op.run, ())

   def stop(self):
      for op in self.ops:
         op.cancel()
      self._event.set()


import sqlite3 #Import the SQLite3 module

class MyDB(object):
   _db_connection = None
   _db_cur = None

   def __init__(self):
      self._db_connection = sqlite3.connect('/var/lib/mumble-server/createcon.sqlite', check_same_thread = False)
      self._db_cur = self._db_connection.cursor()
      self.initDatabase()

   def initDatabase(self):
      if self._db_connection:
         self._db_cur.execute('''CREATE TABLE IF NOT EXISTS controlled_channels (
                   sid INTEGER NOT NULL,
                   cid INTEGER NOT NULL,
                   user INTEGER NOT NULL,
                   cdate INTEGER NOT NULL,
                   timeout INTEGER NOT NULL,
                   PRIMARY KEY (sid, cid));''')


         self._db_cur.execute('''CREATE TABLE IF NOT EXISTS controlled_channels_stats (
                   id INTEGER PRIMARY KEY,
                   sid INTEGER NOT NULL,
                   cid INTEGER NOT NULL,
                   date INTEGER NOT NULL);''')

         self._db_connection.commit()

   def channelcreated(self, server, channelid, user):
      current_time = datetime.now()
      result = self._db_cur.execute('''INSERT OR REPLACE INTO controlled_channels(sid, cid, user, cdate) VALUES (:sid, :cid, :user, :cdate);''', {"sid": int(server.id()), "cid": channelid, "user": user, "cdate": current_time})
      self._db_connection.commit()
      return result

   def setchannelused(self, server, channelid):
      current_time = datetime.now()
      result = self._db_cur.execute('''INSERT OR REPLACE INTO controlled_channels_stats(sid, cid, date) VALUES (:sid, :cid, :cdate);''', {"sid": int(server.id()), "cid": channelid, "cdate": current_time})
      self._db_connection.commit()
      return result

   def channelremoved(self, server, channelid):
      result = self._db_cur.execute('''DELETE FROM controlled_channels WHERE sid = :sid AND cid  = :cid;''', {"sid": int(server.id()), "cid": channelid})
      self._db_connection.commit()
      return result

   def getchannels(self):
      result = self._db_cur.execute('''SELECT sid, cid, user, cdate FROM controlled_channels;''')
      return self._db_cur.fetchall()

   def channelUsed5hours(self):
      result = self._db_ur.execute(''' SELECT Nutz FROM (SELECT count(date) as Nutz, channels.name Channelname FROM channels LEFT JOIN activities ON channels.id == activities.channel AND (activities.date >= date('now','-5 hours') ) GROUP BY channels.id ORDER BY Nutz DESC,channels.name) WHERE Nutz > 0;''')

   def channelUserCount(self, server, user):
      result = self._db_cur.execute(''' SELECT count(user) FROM controlled_channels WHERE user == :userid;''',{"userid": int(user)})
      return int(self._db_cur.fetchall()[0][0])

   def query(self, query, params):
      result = self._db_cur.execute(query, params)
      self._db_connection.commit()
      return result

   def __del__(self):
      self._db_connection.close()


database = MyDB()

class createcon(MumoModule):
    default_config = {'createcon':(
                                ('servers', commaSeperatedIntegers, []),
                                ('keyword', str, '!createcon')
                                )
                    }

    sched01 = sched.scheduler(time.time, time.sleep)

    tree = None

    def __init__(self, name, manager, configuration = None):
        MumoModule.__init__(self, name, manager, configuration)
        self.murmur = manager.getMurmurModule()
        self.keyword = self.cfg().createcon.keyword
        self.watchdog = None

    def connected(self):
        manager = self.manager()
        log = self.log()
        log.debug("Register for Server callbacks")

        servers = self.cfg().createcon.servers
        if not servers:
            servers = manager.SERVERS_ALL

        manager.subscribeServerCallbacks(self, servers)

        if not self.watchdog:
           self.watchdog = Timer(3, self.handlewatchdog)
           self.watchdog.start()

    def disconnected(self):
        if self.watchdog:
            self.watchdog.stop()
            self.watchdog = None


    def handlewatchdog(self):

        meta = self.manager().getMeta()

        servers = meta.getBootedServers()

        for row in database.getchannels():

           server = meta.getServer(row[0]) 

           self.log().debug("%s %s %s %s" % (row[0], row[1], row[2], row[3]))

           if self.getBranchUsed(server, row[1]):
              database.setchannelused(server, row[1])
           else:
              if ( len(server.getChannelState(row[1]).description) < 10 ):
                 database.channelremoved(server, row[1])
                 server.removeChannel(row[1])


        # Renew the timer
        self.watchdog = Timer(10*60, self.handlewatchdog)  
        self.watchdog.start()

    def do_something(self, sc):

        for row in database.getchannels():
              self.log().debug("%s %s %s %s" % (row[0], row[1], row[2], row[3]))

              meta = self.manager().getMeta()

              servers = meta.getBootedServers()

              for server in servers:
                 if not server: continue
                 if server:
                    t = self.getBranch(server, row[1])
                    self.log().debug("yyy2 %s %s  " % (getBranchUsed(server, row[1]), json.dumps(t)))

              sc.enter(10, 1, self.do_something, (sc,))
              sc.run();

    def sendMessage(self, server, user, message, msg):
        if message.channels:
            server.sendMessageChannel(user.channel, False, msg)
        else:
            server.sendMessage(user.session, msg)
            server.sendMessage(message.sessions[0], msg)



    def treeUsed(self, tree, channelID, sum = False, result = 0):
        if tree.c.id == channelID:
           sum = True

        if len(tree.users) >= 1:
           result += 1

        for list in tree.children:
            treeUsed(list, channelID, sum, result)

        return


    def getBranchUsed(self, server, channelid):
        for channel in self.getBranch(server, channelid):
           if not channel: continue

           if channel:

              if channel[1] > 0:
                 return True
        return False

    def getBranch(self, server, channelid):
        result = []
        self.getBranch2(server.getTree(), channelid, result)
        return result

    def getBranch2(self, tree, channelid, result, active = False, parent=None):

        if (tree.c.id == channelid):
            active = True

        if (len(tree.users) >= 1) & (active):
            data = [tree.c.id, len(tree.users) ]

            result.append(data)

        for list in tree.children:
            self.getBranch2(list, channelid, result, active )
        return


    def createSimpleConf(self, server, user):

        channelid=server.addChannel("Konferenzraum von " + user.name,81)
        server.setACL(channelid,
              [self.murmur.ACL(applyHere = True,
              applySubs = True,
              userid = user.userid,
              allow = 0x241)],
              [],True)

        return channelid


    def createPodium(self, server, channelid):
        newchannelid=server.addChannel("Podium", channelid)
#        server.setACL(newchannelid,
#              [self.murmur.ACL(applyHere = True,
#              applySubs = True,
#              userid = user.userid,
#              allow = 0x01)],
#              [],True)
        return newchannelid

    def createSaalmicro(self, server, channelid):
        newchannelid=server.addChannel("Saalmikrofon", channelid)
#        server.setACL(newchannelid,
#              [self.murmur.ACL(applyHere = True,
#              applySubs = True,
#              userid = user.userid,
#              allow = 0x01)],
#              [],True)
        return newchannelid

    def createListener(self, server, channelid):
        newchannelid=server.addChannel("Zuhörende", channelid)
#        server.setACL(newchannelid,
#              [self.murmur.ACL(applyHere = True,
#              applySubs = True,
#              userid = "@in",
#              disallow = 0x08)],
#              [],True)
        return newchannelid

    def createListener2(self, server, channelid):
#        acl= [self.murmur.ACL(applyHere = True,
#              applySubs = True,
#              userid = user.userid,
#              disallow = 0x08)]
        result = []

        newchannelid=server.addChannel("Zuhörende-PRO", channelid)
        result.append(newchannelid)
#        server.setACL(newchannelid, acl, [], True)
        newchannelid=server.addChannel("Zuhörende-NEUTRAL", channelid)
        result.append(newchannelid)
#        server.setACL(newchannelid, acl, [], True)
        newchannelid=server.addChannel("Zuhörende-CONTRA", channelid)
        result.append(newchannelid)
#        server.setACL(newchannelid, acl, [], True)
        return result




    #
    #--- Server callback functions
    #

    def userTextMessage(self, server, user, message, current=None):

        if message.text.startswith(self.keyword) and \
            (len(message.sessions) == 1 or
              (len(message.channels) == 1 and \
              message.channels[0] == user.channel)):

            tuname = message.text[len(self.keyword):].strip()

            profilename = message.text[len(self.keyword):].strip()

            self.log().debug("User %s (%d|%d) on server %d asking for '%s'", user.name, user.session, user.userid, server.id(), tuname)

            userstate = server.getState(int(user.session))

            if userstate.channel != 81:
                msg = "Falscher Channel"
                self.sendMessage(server, user, message, msg)
                return

            # TODO nur registrierte user 

            if (user.userid == -1):
                msg = "Nur registrierte Nutzer können Konferenzräume anlegen"
                self.sendMessage(server, user, message, msg)
                return

            if (database.channelUserCount(server, user.userid) >= 3):
                msg = "Die maximale Anzahl der Räume ist erreicht."
                self.sendMessage(server, user, message, msg)
                self.log().debug(database.channelUserCount(server, user.userid))

                return

            ACL = self.murmur.ACL
            PERM_CHANNEL = self.murmur.PermissionWrite

            # Check for self referencing
            if profilename == "simple":
                msg = "Konferenzraum wird angelegt"
                self.sendMessage(server, user, message, msg)
                newChannelID = self.createSimpleConf(server, user)
                user.channel = newChannelID
                server.setState(user)
                database.channelcreated(server, newChannelID, user.userid)

                return

            if profilename == "podium":
                newChannelID = self.createSimpleConf(server, user)
                acllist = [] 
                for list in server.getACL(newChannelID)[0]:
                    if (list.inherited != True):
                        acllist.append(list)

                acllist.append(self.murmur.ACL(applyHere = True,
                           applySubs = False,
                           userid = -1,
                           group ="all",
                           deny = 0x04))
                server.setACL(newChannelID, acllist, [], True)

#                current_time = datetime.now()

#                self.database.query('''INSERT OR REPLACE INTO controlled_channels(cid, date) VALUES (?,?);''',(newChannelID, current_time))

                database.channelcreated(server, newChannelID, user.userid)

                c1 = self.createPodium(server, newChannelID)

                user.channel = c1
                server.setState(user)

                c2 = self.createSaalmicro(server, newChannelID)
                c3 = self.createListener(server, newChannelID)

                acllist = [] 
                for list in server.getACL(c3)[0]:
                    if (list.inherited != True):
                        acllist.append(list)


                acllist.append(self.murmur.ACL(applyHere = True,
                           applySubs = True,
                           userid = -1,
                           group ="in",
                           deny = 0x08))
                server.setACL(c3, acllist, [], True)

                t = server.getChannelState(c3)
                t.links = [c1, c2, c3]
                server.setChannelState(t)

                return


            if profilename == "podium2":
                newChannelID = self.createSimpleConf(server, user)
                acllist = [] 
                for list in server.getACL(newChannelID)[0]:
                    if (list.inherited != True):
                        acllist.append(list)

                acllist.append(self.murmur.ACL(applyHere = True,
                           applySubs = False,
                           userid = -1,
                           group ="all",
                           deny = 0x04))
                server.setACL(newChannelID, acllist, [], True)

#                current_time = datetime.now()

 #               self.database.query('''INSERT OR REPLACE INTO controlled_channels(cid, date) VALUES (?,?);''',(newChannelID, current_time))

                database.channelcreated(server, newChannelID, user.userid)

                c1 = self.createPodium(server, newChannelID)

                user.channel = c1
                server.setState(user)

                c2 = self.createSaalmicro(server, newChannelID)
                c3 = self.createListener2(server, newChannelID)

                acllist = [] 
                for list in server.getACL(c3[0])[0]:
                    if (list.inherited != True):
                        acllist.append(list)


                acllist.append(self.murmur.ACL(applyHere = True,
                           applySubs = True,
                           userid = -1,
                           group ="in",
                           deny = 0x08))

                t = server.getChannelState(c1)
                t.links = [c2]

                for channelid in c3:
                    server.setACL(channelid, acllist, [], True)
                    t.links.append(channelid)

                server.setChannelState(t)

                return

#            if profilename == "podium2":
#                newChannelID = self.createSimpleConf(server, user)
#                c1 = self.createPodium(server, newChannelID)
#                c2 = self.createSaalmicro(server, newChannelID)
#                c3 = self.createListener2(server, newChannelID)
#                t = server.getChannelState(newChannelID)
#                t.links = [c1, c2, c3]
#                server.setChannelState(t)
#                self.createPodium(server, newChannelID)
#                self.createSaalmicro(server, newChannelID)
#                self.createListener2(server, newChannelID)
#                return

            # Check online users
            for cuser in server.getUsers().itervalues():
                if tuname == cuser.name:
                    msg = "User '%s' is currently online, has been idle for %s" % (tuname, timedelta(seconds=cuser.idlesecs))
                    self.sendMessage(server, user, message, msg)
                    return

            # Check registrations
            for cuid, cuname in server.getRegisteredUsers(tuname).iteritems():
                if cuname == tuname:
                    ureg = server.getRegistration(cuid)
                    if ureg:
                        msg = "User '%s' was last seen %s UTC" % (tuname, ureg[self.murmur.UserInfo.UserLastActive])

                        self.sendMessage(server, user, message, msg)
                        return

            msg = "<br>Bitte gebe ein Konferenzraumprofil an: <br>\nsimple : Ein Raum mit Adminrechten"
            self.sendMessage(server, user, message, msg)


    def userConnected(self, server, state, context = None): pass

    def userDisconnected(self, server, state, context = None): pass

    def userStateChanged(self, server, state, context = None): pass

    def channelCreated(self, server, state, context = None): pass

    def channelRemoved(self, server, state, context = None):
        self.log().debug("State.id: %s", (state.id))
        database.channelremoved(server, int(state.id))


    def channelStateChanged(self, server, state, context = None): pass
