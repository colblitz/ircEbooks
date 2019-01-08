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
from VerticalScrolledFrame import *

import irc.client

DEBUG = False

IRC_SERVER = "irc.irchighway.net"
IRC_PORT = 6667
IRC_CHANNEL = "#ebooks"
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
        self.latestFilename = None
        # https://github.com/gehaxelt/python-rss2irc/pull/25
        self.connection.buffer_class.errors = 'replace'

    def log(self, s):
        tLog("Client", s)

    def debug(self, s):
        if DEBUG:
            self.log(s)

    def on_welcome(self, connection, event):
        connection.join(self.target)

    def on_join(self, connection, event):
        if event.source.nick == BOT_NICK:
            self.log("Joined channel")

    def send_privmsg(self, message):
        self.log("Pming {}: \"{}\"".format(self.handler, message))
        self.connection.privmsg(self.handler, message)

    def send_channel(self, message):
        self.log("To channel {}: {}".format(self.target, message))
        self.connection.privmsg(self.target, message)

    def do_search(self, searchText):
        self.latestFile = None
        self.latestFilename = None
        message = "@search {}".format(searchText)
        self.log("Searching for \"{}\"".format(searchText))
        self.log("To channel {}: \"{}\"".format(self.target, message))
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
        self.latestFilename = filename
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
    tLog("Processor", "Unzipping file")
    with zipfile.ZipFile(filename) as zf, open(newfile, 'w') as f:
        if len(zf.namelist()) > 1:
            tLog("Processor", "File format has changed, more than one file in search zip")
            sys.exit(1)
        txtfile = zf.namelist()[0]
        f.write(zf.read(txtfile))

    tLog("Processor", "Parsing file")
    available = {}
    with open(newfile, 'r') as f:
        for line in f:
            if line[0] != '!':
                continue
            if 'epub' not in line.lower():
                continue
            i1 = line.find(' ')
            i2 = line.find('::')
            if i2 == -1:
                i2 = line.find('\r')
            user = line[:i1]
            file = line[i1:i2].strip()

            if file not in available:
                available[file] = set()
            available[file].add(user.replace("!", ""))

    tLog("Processor", "Got {} unique options".format(len(available)))
    return available


client = None
elements = []
searchField, optionsPanel, optionsFilter, optionsList = None, None, None, None

def buttonPress(user, file):
    tLog("GUI", "ButtonPress for user {}, file {}".format(user, file))
    command = "!{} {}".format(user, file)
    tLog("GUI", "Command: {}".format(command))
    client.send_channel(command)

def updateFilter():
    limit = int(optionsFilter.get())
    tLog("GUI", "Limit: {}".format(limit))

    # hide all elements, show the ones that pass the filter
    nrow = 0
    for r in elements:
        ncol = 0
        for e in r:
            e.grid_forget()
        if len(r) - 1 >= limit:
            for e in r:
                e.grid(row=nrow, column=ncol, sticky=W+E)
                ncol += 1
            nrow += 1

def doSearch():
    global elements, optionsFilter
    searchText = searchField.get()
    tLog("GUI", "Do search for: {}".format(searchText))
    searchField.delete(0,END)

    # reset buttons
    for r in elements:
        for e in r:
            e.destroy()
    elements = []

    tLog("GUI", "Sending to client")
    client.do_search(searchText)

    # wait until we got the file
    while client.latestFile is None:
        tLog("GUI", "Waiting for file...")
        time.sleep(2)
    tLog("GUI", "Got file, going to process")

    available = processFile(client.latestFilename)
    maxPeople = 0
    for key in available:
        if len(available[key]) > maxPeople:
            maxPeople = len(available[key])

    # create filter and buttons
    if optionsFilter is None:
        optionsFilter = Spinbox(optionsPanel, from_=1, to=maxPeople, command=updateFilter)
        optionsFilter.pack(side=TOP, anchor='w')
    else:
        optionsFilter.config(to=maxPeople)
    optionsList.pack(side=TOP, expand=YES, fill=BOTH)
    nrow = 0
    for key in sorted(available.iterkeys()):
        ncol = 0
        elements.append([])
        people = list(available[key])
        label = Label(optionsList, justify=LEFT, anchor='w', text=key)
        label.grid(row=nrow, column=ncol, sticky=W+E)
        elements[nrow].append(label)

        for person in people:
            ncol += 1
            button = Button(optionsList, text=person, command=lambda file=key, user=person: buttonPress(user, file))
            button.grid(row=nrow, column=ncol, sticky=W+E)
            elements[nrow].append(button)

        nrow += 1


def makeGUI():
    global searchField, optionsPanel, optionsList
    tLog("GUI", "Creating gui")

    root = Tk()
    row = Frame(root)
    searchField = Entry(row)
    but = Button(row, text='Search', command=doSearch)

    optionsPanel = Frame(root)
    optionsList = VerticalScrolledFrame(optionsPanel)

    row.pack(side=TOP, fill=X)
    searchField.pack(side=LEFT, expand=YES, fill=X)
    but.pack(side=RIGHT)
    optionsPanel.pack(side=TOP, expand=YES, fill=BOTH)
    root.bind('<Return>', (lambda event: doSearch()))

    root.mainloop()


if __name__ == "__main__":
    clientThread = ClientThread(name="ClientThread")
    clientThread.daemon = True
    clientThread.start()

    tLog("Main", "Waiting 35 seconds before creating GUI")
    time.sleep(35)
    client = clientThread.getClient()

    makeGUI()
    tLog("Main", "End of Main")