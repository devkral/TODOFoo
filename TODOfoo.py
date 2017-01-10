#! /usr/bin/env python3

"""
LICENSE: MIT

"""

import urwid
import datetime
import sys
import logging
import os
import copy
import threading

filter_while_using = False
default_removetime = 60*60*24*10
default_path = os.path.join(os.path.expandvars("$HOME"), ".TODOfoo.txt")

def create_now_datetime():
    ll = datetime.datetime.now()
    return datetime.datetime(ll.year, ll.month, ll.day, ll.hour, ll.minute)

def split_hour_minute(timestr):
    splitted = timestr.split(":", 1)
    if len(splitted) == 1:
        return int(splitted[0]), 0
    else:
        return int(splitted[0]), int(splitted[1])

def analyse_time(timestr):
    splitted = timestr.split("-")
    ll = create_now_datetime()
    if len(splitted) == 1:
        return datetime.datetime(ll.year, ll.month, ll.day, *split_hour_minute(timestr[0]))
    elif len(splitted) == 2:
        return datetime.datetime(int(splitted[0]), int(splitted[1]), 1, 0, 0)
    elif len(splitted) == 3:
        return datetime.datetime(int(splitted[0]), int(splitted[1]), int(splitted[2]), 0, 0)
    elif len(splitted) == 4:
        return datetime.datetime(int(splitted[0]), int(splitted[1]), int(splitted[2]), *split_hour_minute(splitted[3]))
    raise

def analyse_timedelta(timestr):
    splitted = timestr.split("-", 1)
    hours, minutes = split_hour_minute(splitted[-1])
    days = 0
    if len(splitted) == 2:
        days += int(splitted[0])
    return datetime.timedelta(days=days, hours=hours, minutes=minutes)

def analyse_headerelem(elem):
    splitted = elem.split(":", 1)
    if len(splitted) == 2:
        c, val = splitted
        c.strip().rstrip()
    else:
        c, val = splitted[0], None
    c.strip().rstrip()
    if c == "start":
        return "start", analyse_time(val)
    elif c == "stop":
        return "stop", analyse_time(val)
    elif c == "repeat":
        return "repeat", analyse_timedelta(val)
    elif c == "x":
        return "checked", True
    return None

def analyse_item(item, defaultchecked=False):
    header, body = item.split("::", 1)
    body = body.rstrip()
    sheader = header.split(",")
    name = sheader[0]
    start, stop, repeat, checked = None, None, None, defaultchecked
    for elem in sheader[1:]:
        try:
            returned = analyse_headerelem(elem)
            if not returned:
                logging.warning("unrecognized header field")
            elif returned[0] == "start":
                start = returned[1]
            elif returned[0] == "stop":
                stop = returned[1]
            elif returned[0] == "repeat":
                repeat = returned[1]
            elif returned[0] == "checked":
                checked = True
        except:
            logging.warning("invalid header element: %s", elem)

    if stop and start and stop < start:
        # do not allow stop before start, rescue
        logging.warning("stop before start, rescue %i, %i", start, stop)
        start = stop
    return name, body, checked, start, stop, repeat

def verify_item(item):
    try:
        header, body = item.split("::", 1)
        sheader = header.split(",")
        start, stop = None, None
        #name = sheader[0]
        for elem in sheader[1:]:
            returned = analyse_headerelem(elem)
            if not returned:
                raise
            elif returned[0] == "start":
                start = returned[1]
            elif returned[0] == "stop":
                stop = returned[1]
        if stop and start and stop < start:
            raise
    except:
        return False
    return True



def extract_keys(list_item):
    """ extract keys for sorting
        list_item def: name, body, checked, start, stop, repeat """
    now = datetime.datetime.now()
    if list_item[2] and list_item[4] and (not list_item[3] or list_item[3]>now):
        return 0, list_item[2].total_seconds(), 0, list_item[3].total_seconds()
    elif list_item[2] and list_item[3]:
        return 0, list_item[2].total_seconds(), 0, list_item[3].total_seconds()
    elif list_item[2]:
        return 0, list_item[2].total_seconds(), 1, -1
    else:
        return 1, -1, -1, -1

def extract_widgetkeys(list_item):
    """ extract keys from a widget,checked does not matter yet so just analyse label """
    # checked incorrect, but does not matter in calculation
    return extract_keys(analyse_item(list_item.label))

def filter_widget(removetime):
    def _filter_widget(list_item):
        if not verify_item(list_item.label):
            return False
        lll = analyse_item(list_item.label)
        if lll[4] and lll[4] < removetime:
            return False
        return True
    return _filter_widget

def tup_to_text(tup, nochecked=False):
    # name, body, checked, start, stop, repeat
    header = tup[0]
    if not nochecked:
        if tup[2]:
            header += ",x"
    if tup[3]:
        header += ",start:{}".format(tup[3].strftime("%Y-%m-%d-%H:%M"))
    if tup[4]:
        header += ",stop:{}".format(tup[4].strftime("%Y-%m-%d-%H:%M"))
    if tup[5]:
        # hours is in seconds
        hours, minutes = divmod(tup[5].seconds, 3600)
        # hours are correct
        # minutes is in seconds
        minutes =  minutes // 60
        # minutes are correct
        if tup[5].days == 0:
            header += ",repeat:{}:{}".format(hours, minutes)
        else:
            header += ",repeat:{}-{}:{}".format(tup[5].days, hours, minutes)
    return "{header}::{body}".format(header=header, body=tup[1])

def calc_start(now, start, stop, repeat, checked):
    """ calculate start and checked """
    if repeat and start < now:
        if not stop or stop-start>repeat:
            _start = copy.copy(start)
            while _start < now and (not stop or _start<stop-repeat):
                _start += repeat
            if _start > now:
                checked = False
            return _start, checked
    return start, checked

def text_to_widgets(tlist, chfunc):
    newlist = []
    now = create_now_datetime()
    for elem in tlist:
        try:
            name, body, checked, start, stop, repeat = analyse_item(elem)
            start, checked = calc_start(now, start, stop, repeat, checked)
            cb = urwid.CheckBox(tup_to_text((name, body, checked, start, stop, repeat), True), state=checked)
            urwid.connect_signal(cb, 'change', chfunc)
            newlist.append(cb)
        except Exception as exc:
            logging.warning("Invalid elem: %s", elem)
    return newlist

def widgets_to_text(tlist):
    newlist = []
    for elem in tlist:
        splitted = elem.label.split("::", 1)
        if elem.state:
            checked = ",x"
        else:
            checked = ""
        # name, body, checked, start, stop, repeat
        newlist.append("{}{}::{}".format(splitted[0], checked, splitted[1]))
    return newlist

class FooPile(urwid.Pile):
    def keypress(self, size, key):
        if key == "tab":
            self.focus_position = (self.focus_position+1)%2
            return False
        return super().keypress(size, key)


class FooListBox(urwid.ListBox):
    """ Listbox which allows saving and setting text """
    set_cb = None
    save_cb = None
    doubledelete = False
    def __init__(self, body, set_cb, save_cb):
        super().__init__(body)
        self.set_cb = set_cb
        self.save_cb = save_cb

    def keypress(self, size, key):
        if key == "delete":
            if not self.body[self.focus_position].state:
                if not self.doubledelete:
                    self.doubledelete = True
                    return False
            del self.body[self.focus_position]
            self.save_cb()
            return False
        self.doubledelete = False
        if key == "right":
            self.set_cb(self.body[self.focus_position])
            return False
        return super().keypress(size, key)


class TODOFoo(logging.Handler):
    loop = None
    # initial widgetlist
    _widgetlist = None
    # listbox widget
    listtodos = None
    # filename
    savefile = None
    addbut = None
    # error presentation widget
    errorpres = None
    def __init__(self, savefile, removetime=default_removetime):
        super().__init__()
        self.savefile = savefile
        try:
            self.load()
        except FileNotFoundError:
            self._widgetlist = []
        self.listtodos = FooListBox(urwid.SimpleListWalker(self._widgetlist), self.change_edit, self.save)
        ltbuild = urwid.BoxAdapter(self.listtodos, 20)
        self.addbut = urwid.Edit("Add/Edit TODO: ")
        self.errorpres = urwid.Text("")
        if len(self.listtodos.body) > 0:
            fitem = 0
        else:
            fitem = 1
        pile = FooPile([('pack', ltbuild),('pack', self.addbut), ('pack', self.errorpres)], focus_item=fitem)
        #grid.contents.append(top)
        #grid.contents.append(addbut)
        fill = urwid.Filler(pile, 'bottom')
        self.loop = urwid.MainLoop(fill, unhandled_input=self.globalhandler)

    def emit(self, record):
        self.errorpres.set_text(record.getMessage())

    def change_edit(self, focwidget):
        self.addbut.edit_text = widgets_to_text([focwidget])[0]

    def add_item(self, editwidget):
        text = editwidget.edit_text
        if text == "example":
            now = create_now_datetime()
            nowst = now+datetime.timedelta(days=1)
            now = now.strftime("%Y-%m-%d-%H:%M")
            nowst = nowst.strftime("%Y-%m-%d-%H:%M")
            text = """example,start:{},stop:{},repeat:3:00:: here an example, to modify press: <right>, to delete press: <delete>. Have fun!""".format(now, nowst)
        if verify_item(text):
            now = create_now_datetime()
            name, body, checked, start, stop, repeat = analyse_item(text)
            checked = False
            start = calc_start(now, start, stop, repeat, checked)[0]
            insertpos = -1
            isinlist = False
            lkey = extract_keys((name, body, checked, start, stop, repeat))
            if filter_while_using:
                removefilter = filter_widget(now-datetime.timedelta(seconds=default_removetime))
                for elem in self.listtodos.body:
                    if not removefilter(elem):
                        del elem
            for count, elem in enumerate(self.listtodos.body):
                if elem.label.split("::", 1)[0].split(",", 1)[0] == name:
                    analysed = analyse_item(elem.label)
                    if not start and analysed[3]:
                        start = analysed[3]
                    if not stop and analysed[4]:
                        stop = analysed[4]
                    if not repeat and analysed[5]:
                        repeat = analysed[5]
                    insertpos = count
                    isinlist = True
                    break
                if lkey > extract_widgetkeys(elem) and insertpos == -1:
                    insertpos = max(count-1, 0)

            if not start:
                start = copy.copy(now)
            ll = urwid.CheckBox(tup_to_text((name, body, checked, start, stop, repeat), True), state=checked)
            urwid.connect_signal(ll, 'change', self.save_after_check)
            if isinlist:
                self.listtodos.body[insertpos] = ll
            else:
                self.listtodos.body.insert(insertpos, ll)
            self.save()
            self.errorpres.set_text("")
        else:
            self.errorpres.set_text("Invalid entry format, for help enter example")
    def save_after_check(self, wid, state):
        savet = self.listtodos.body.copy()
        f = savet.index(wid)
        newcheck = urwid.CheckBox(wid.label, state=state)
        urwid.connect_signal(newcheck, 'change', self.save_after_check)
        savet[f] = newcheck
        self.save(savet)
    def save(self, savet=None):
        if not savet:
            savet = self.listtodos.body.copy()
        try:
            os.rename(self.savefile, "{}.backup".format(self.savefile))
        except FileNotFoundError:
            pass
        with open(self.savefile, "w") as ro:
            ro.write('\n'.join(widgets_to_text(savet)))
        try:
            os.remove("{}.backup".format(self.savefile))
        except FileNotFoundError:
            pass

    def load(self):
        with open(self.savefile, "r") as ro:
            removefilter = filter_widget(create_now_datetime()-datetime.timedelta(seconds=default_removetime))
            log = text_to_widgets(ro.readlines(), self.save_after_check)
            self._widgetlist = sorted(filter(removefilter, log), key=extract_widgetkeys)

    def globalhandler(self, key):
        if key == 'enter':
            self.add_item(self.addbut)
        elif key in ('q', 'Q', 'esc'):
            raise urwid.ExitMainLoop()

    def run(self):
        self.loop.run()

if __name__ == "__main__":
    if len(sys.argv) == 1:
        f = TODOFoo(default_path)
    else:
        f = TODOFoo(sys.argv[1])
    logging.getLogger().handlers.clear()
    logging.getLogger().addHandler(f)
    f.run()
