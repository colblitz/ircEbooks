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
        self.connection.buffer_class.errors = 'replace'

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
        self.latestFile = None
        self.latestFilename = None
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
    tLog("Processor", "unzipping")
    with zipfile.ZipFile(filename) as zf, open(newfile, 'w') as f:
        if len(zf.namelist()) > 1:
            print "Oh no"
            return
        txtfile = zf.namelist()[0]
        f.write(zf.read(txtfile))

    tLog("Processor", "parsing")
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
                available[file] = set()
            available[file].add(user.replace("!", ""))

            # print "START", user, "##########", file

    tLog("Processor", "got {} unique options".format(len(available)))
    # for key in sorted(available.iterkeys()):
    #     print "{:100} | {}".format(key, list(available[key]))
    # tLog("PROCESSOR", "got {} unique options".format(len(available)))

    # print "done processing file"
    return available



# https://stackoverflow.com/questions/31762698/dynamic-button-with-scrollbar-in-tkinter-python
class VerticalScrolledFrame(Frame):
    """A pure Tkinter scrollable frame that actually works!

    * Use the 'interior' attribute to place widgets inside the scrollable frame
    * Construct and pack/place/grid normally
    * This frame only allows vertical scrolling
    """
    def __init__(self, parent, *args, **kw):
        Frame.__init__(self, parent, *args, **kw)

        # create a canvas object and a vertical scrollbar for scrolling it
        vscrollbar = Scrollbar(self, orient=VERTICAL)
        vscrollbar.pack(fill=Y, side=RIGHT, expand=FALSE)
        canvas = Canvas(self, bd=0, highlightthickness=0,
                        yscrollcommand=vscrollbar.set)
        canvas.pack(side=LEFT, fill=BOTH, expand=TRUE)
        vscrollbar.config(command=canvas.yview)

        # reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        # create a frame inside the canvas which will be scrolled with it
        self.interior = interior = Frame(canvas)
        interior_id = canvas.create_window(0, 0, window=interior,
                                           anchor=NW)

        # track changes to the canvas and frame width and sync them,
        # also updating the scrollbar
        def _configure_interior(event):
            # update the scrollbars to match the size of the inner frame
            size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
            canvas.config(scrollregion="0 0 %s %s" % size)
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # update the canvas's width to fit the inner frame
                canvas.config(width=interior.winfo_reqwidth())

        interior.bind('<Configure>', _configure_interior)

        def _configure_canvas(event):
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # update the inner frame's width to fill the canvas
                canvas.itemconfigure(interior_id, width=canvas.winfo_width())

        canvas.bind('<Configure>', _configure_canvas)


# root = Tk()
# root.title("Scrollable Frame Demo")
# root.configure(background="gray99")



# lis = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
# for i, x in enumerate(lis):
#     btn = tk.Button(scframe.interior, height=1, width=20, relief=tk.FLAT,
#         bg="gray99", fg="purple3",
#         font="Dosis", text='Button ' + lis[i],
#         command=lambda i=i,x=x: openlink(i))
#     btn.pack(padx=10, pady=5, side=tk.TOP)

# def openlink(i):
#     print lis[i]

# root.mainloop()





client = None
buttons = []
buttonValues = {}
elements = []
searchField = None
gfilter = None

def buttonPress(user, file):
    tLog("GUI", "buttonPress for user {}, file {}".format(user, file))
    command = "!{} {}".format(user, file)
    tLog("GUI", "command would be: {}".format(command))
    global client
    client.send_channel(command)

def updateValue():
    global buttons, buttonValues, gfilter, elements
    limit = int(gfilter.get())
    tLog("GUI", "limit: {}".format(limit))

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

    # for b in buttons:
    #     b.pack_forget()
    #     if len(buttonValues[b]) >= limit:
    #         b.pack(side=TOP)

def doSearch():
    global client, buttons, buttonValues, searchField, gfilter, elements
    searchText = searchField.get()
    tLog("GUI", "doSearch: {}".format(searchText))
    searchField.delete(0,END)

    # reset buttons
    if gfilter is not None:
        gfilter.destroy()
    for b in buttons:
        b.destroy()
    buttonValues = {}
    elements = []

    tLog("GUI", "sending to client")
    client.do_search(searchText)

    # wait until we got the file
    while client.latestFile is None:
        tLog("GUI", "waiting for file...")
        time.sleep(2)
    tLog("GUI", "got file, going to process")

    available = processFile(client.latestFilename)
    maxPeople = 0
    for key in available:
        if len(available[key]) > maxPeople:
            maxPeople = len(available[key])

    w = Spinbox(optionsPanel, from_=1, to=maxPeople, command=updateValue)
    w.pack(side=TOP, anchor='w')
    gfilter = w
    scframe.pack(side=TOP, expand=YES, fill=BOTH)
    nrow = 0
    for key in sorted(available.iterkeys()):
        ncol = 0
        elements.append([])
        label = key
        people = list(available[key])
        label = Label(scframe.interior, justify=LEFT, anchor='w', text=label)
        label.grid(row=nrow, column=ncol, sticky=W+E)
        elements[nrow].append(label)

        for person in people:
            ncol += 1
            button = Button(scframe.interior, text=person, command=lambda file=key, user=person: buttonPress(user, file))
            button.grid(row=nrow, column=ncol, sticky=W+E)
            elements[nrow].append(button)

        nrow += 1





        # label = "({}) {}".format(len(available[key]), key)
        # people = list(available[key])
        # tk.Label(root, text="Hello Tkinter!")
        # button = Button(scframe.interior, anchor="w", text=label, command=lambda text = people: buttonPress(people))
        # button.pack(side=TOP)
        # buttons.append(button)
        # buttonValues[button] = people


    #     print "{:100} | {}".format(key, list(available[key]))

    # for a in range(random.randint(5, 20)):
    #     l = range(random.randint(1, 5))
    #     button = Button(optionsPanel, text=str(a)+str(l), command=lambda text = str(a)+str(l): buttonPress(text))
    #     button.pack(side=TOP)
    #     buttons.append(button)
    #     buttonValues[button] = l


def makeGUI():
    global searchField, optionsPanel, scframe

    tLog("GUI", "creating gui")

    root = Tk()
    row = Frame(root)
    ent = Entry(row)
    searchField = ent
    but = Button(row, text='Search', command=doSearch)

    options = Frame(root)
    optionsPanel = options
    scframe = VerticalScrolledFrame(options)

    row.pack(side=TOP, fill=X)
    ent.pack(side=LEFT, expand=YES, fill=X)
    but.pack(side=RIGHT)
    options.pack(side=TOP, expand=YES, fill=BOTH)
    # root.bind('<Return>', (lambda event, e=ents: fetch(e)))
    root.bind('<Return>', (lambda event: doSearch()))

    root.mainloop()


if __name__ == "__main__":
    clientThread = ClientThread(name="ClientThread")
    clientThread.daemon = True
    clientThread.start()

    time.sleep(35)
    client = clientThread.getClient()

    makeGUI()
    print "after"
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