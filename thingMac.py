import os
import random
import shlex
import struct
import sys
import threading
import time
import traceback
import zipfile

from Tkinter import *

import irc.client

DEBUG = False

IRC_SERVER = "irc.irchighway.net"
IRC_PORT = 6667
IRC_CHANNEL = "#testblah1234"
BOT_NICK = "fetcher"
HANDLER = "colblitz"

def tLog(tName, s):
    t = time.strftime("%H:%M:%S", time.gmtime())
    sys.stdout.write("[{} {:12}] {}\n".format(t, tName, s))
    sys.stdout.flush()

class IRCCat(irc.client.SimpleIRCClient):
    def __init__(self, target, handler):
        irc.client.SimpleIRCClient.__init__(self)
        self.target = target
        self.received_bytes = 0
        self.handler = handler
        self.latestFile = None

    def log(self, s):
        tLog("Client", s)

    def debug(self, s):
        if DEBUG:
            self.log(s)

    def on_welcome(self, connection, event):
        connection.join(self.target)

    def on_join(self, connection, event):
        self.log("Joined")

    def send_privmsg(self, message):
        self.log("Pming {}: {}".format(self.handler, message))
        self.connection.privmsg(self.handler, message)

    def send_channel(self, message):
        self.log("To channel {}: {}".format(self.target, message))
        self.connection.privmsg(self.target, message)

    def do_search(self, searchText):
        message = "@search {}".format(searchText)
        self.log("Doing search for {}".format(message))
        self.connection.privmsg(self.target, message)

    def on_privmsg(self, connection, event):
        message = event.arguments[0]
        self.log("Got privmsg from {}: {}".format(event.source.nick, message))

        if message == "quit":
            self.connection.disconnect()
            sys.exit(0)
        elif message == "try":
            self.do_search("terry brooks")

    def on_ctcp(self, connection, event):
        self.debug(event)
        payload = event.arguments[1]
        if "SEND" not in payload:
            return
        parts = shlex.split(payload)
        command, filename, peer_address, peer_port, size = parts
        if command != "SEND":
            return

        self.log("Got send request from {} for {}".format(event.source.nick, filename))
        self.filename = os.path.basename(filename)
        self.file = open(self.filename, "wb")
        peer_address = irc.client.ip_numstr_to_quad(peer_address)
        peer_port = int(peer_port)
        self.dcc = self.dcc_connect(peer_address, peer_port, "raw")

    def on_dccmsg(self, connection, event):
        data = event.arguments[0]
        self.file.write(data)
        self.received_bytes = self.received_bytes + len(data)
        self.dcc.send_bytes(struct.pack("!I", self.received_bytes))

    def on_dcc_disconnect(self, connection, event):
        self.file.close()
        self.latestFile = self.file
        self.log("Received file {} ({} bytes).".format(self.filename, self.received_bytes))
        # ?? - self.connection.quit()

    def on_disconnect(self, connection, event):
        self.log("Disconnecting")
        sys.exit(0)




class ClientThread(threading.Thread):
    def log(self, s):
        tLog(self.getName(), s)

    def run(self):
        self.log("Starting client thread")
        if not irc.client.is_channel(IRC_CHANNEL):
            self.log("Not a channel: {}".format(IRC_CHANNEL))
            return

        self.client = IRCCat(IRC_CHANNEL, HANDLER)

        try:
            self.client.connect(IRC_SERVER, IRC_PORT, BOT_NICK)
        except Exception as e:
            self.log("Error: " + str(e))
            traceback.print_exc()
            sys.exit(1)

        self.client.start()

    def getClient(self):
        return self.client

def processFile(filename):
    newfile = filename[:-4]
    with zipfile.ZipFile(filename) as zf, open(newfile, 'w') as f:
        if len(zf.namelist()) > 1:
            print "Oh no"
            return
        txtfile = zf.namelist()[0]
        f.write(zf.read(txtfile))

    available = {}
    with open(newfile, 'r') as f:
        for line in f:
            if line[0] != '!':
                continue
            if 'epub' not in line.lower():
                continue
            # print list(line)
            i1 = line.find(' ')
            i2 = line.find('::')
            if i2 == -1:
                i2 = line.find('\r')
            # print i2
            user = line[:i1]
            file = line[i1:i2].strip()

            i3 = file.rfind('.')
            fname = file[:i3]
            ftype = file[i3:]

            if file not in available:
                available[file] = {}
            available[file].add(user)

            # print "START", user, "##########", file

    for key in sorted(available.iterkeys()):
        print "{:100} | {}".format(key, list(available[key]))

    print "done processing file"




# if __name__ == "__main__":
#     # clientThread = ClientThread(name="ClientThread")
#     # clientThread.daemon = True
#     # clientThread.start()

#     # time.sleep(10)
#     # c = clientThread.getClient()

#     c = None

#     guiThread = GuiThread(c, name="GuiThread")
#     guiThread.daemon = True
#     guiThread.start()

#     # # c.send_privmsg("hi after 10 seconds")
#     # # time.sleep(10)
#     # # c.send_privmsg("hi again after 10 seconds")
#     # # c.do_search("terry brooks")
#     while True:
#         time.sleep(1)

    # filename = "SearchBot_results_for__adrian_tchaikovsky.txt.zip"
    # unzipFile(filename)
    # txtName = filename[:-4]
    # print txtName
    # parseFile(txtName)
    # processFile(filename)



options = ["asdf", "lgijwhoi4gh", "owhhuwiuh3"]
buttons = []
buttonValues = {}
gfilter = None

def buttonPress(a):
    print a

def updateValue():
    global options, buttons, buttonValues, gfilter
    limit = int(gfilter.get())
    print "limit: ", limit

    for b in buttons:
        b.pack_forget()
        if len(buttonValues[b]) >= limit:
            b.pack(side=TOP)


def doSearch():
    global options, buttons, buttonValues, gfilter
    searchText = searchField.get()
    print "doSearch: {}".format(searchText)
    searchField.delete(0,END)

    for b in buttons:
        b.destroy()
    buttonValues = {}

    w = Spinbox(optionsPanel, from_=1, to=5, command=updateValue)
    w.pack(side=TOP)
    gfilter = w

    for a in range(random.randint(5, 20)):
        l = range(random.randint(1, 5))
        button = Button(optionsPanel, text=str(a)+str(l), command=lambda text = str(a)+str(l): buttonPress(text))
        button.pack(side=TOP)
        buttons.append(button)
        buttonValues[button] = l



root = Tk()
row = Frame(root)
ent = Entry(row)
searchField = ent
but = Button(row, text='Search', command=doSearch)

options = Frame(root)
optionsPanel = options

row.pack(side=TOP, fill=X)
ent.pack(side=LEFT, expand=YES, fill=X)
but.pack(side=RIGHT)
options.pack(side=TOP, fill=X)
# root.bind('<Return>', (lambda event, e=ents: fetch(e)))
root.bind('<Return>', (lambda event: doSearch()))

root.mainloop()