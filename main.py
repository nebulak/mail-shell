from __future__ import unicode_literals
import imaplib
import re
import email
import email.header
import configparser
from bs4 import BeautifulSoup
# from plugins import tor
from tor import TorPlugin
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit import prompt
from prompt_toolkit.contrib.completers import WordCompleter
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import style_from_dict
from prompt_toolkit.token import Token


class MailClient:
    """
    MailClient is the core of the mail-shell functionality.
    """
    def __init__(self):
        self.hostname = ""
        self.username = ""
        self.password = ""
        self.is_connected = False
        self.connection = None
        self.accounts = []
        self.plugins = []
        self.path = ""
        self.tor = TorPlugin(self)
        self.tor_status = ""

    def update_tor_status(self, line):
        self.tor_status = line

    def connect(self, hostname, username, password):
        self.tor.pre_connect()
        self.connection = imaplib.IMAP4_SSL(hostname)
        try:
            self.connection.login(username, password)
        except Exception as err:
            print('ERROR:', err)
            return
        self.username = username
        self.password = password
        self.hostname = hostname
        self.is_connected = True

    def reconnect(self):
        print("RECONNECT")
        self.deconnect()
        self.tor.pre_connect()
        self.connection = imaplib.IMAP4_SSL(self.hostname)
        try:
            self.connection.login(self.username, self.password)
        except Exception as err:
            print('ERROR:', err)
            return

        if(self.path != ""):
            # Remove leading slash e.g. /INBOX -> INBOX
            print("PATH: " + self.path)
            if self.path[0] == '/':
                self.path = self.path[1:]
            paths = self.path.split("/")
            print(paths)
            for i in range(1, len(paths)):
                #rc, data = self.connection.select(self.path)
                print(paths[i])
                rc, data = self.connection.select(paths[i])
                if rc == "NO":
                    print("path does not exist!")
                    print(self.path)
                    return

    def deconnect(self):
        self.connection.logout()
        self.tor.post_deconnect()

    def ls(self):
        # get mail account if we are on root path
        if Path.get_depth(self.path) == 0:
            # TODO: delete
            # if self.path == "":
            for account in self.accounts:
                print(account.username)
                return

        # get mail directories if path_depth == 1
        if Path.get_depth(self.path) == 1:
            rc, data = self.connection.list()

            for line in data:
                flags, delimiter, mailbox_name = self._parse_list_response(line)
                print(mailbox_name)
            return

        # get message headers
        #self.connection.select(self.path, readonly=True)
        # rc, data = self.connection.search(None, 'ALL')

        # search for uids
        rc, data = self.connection.uid('search', None, 'ALL')
        mail_ids = data[0]
        id_list = mail_ids.split()
        first_email_id = int(data[0].split()[0])
        latest_email_id = int(data[0].split()[-1])

        for i in range(latest_email_id, first_email_id, -1):
            typ, data = self.connection.uid('fetch', str(i), '(RFC822)')

            for response_part in data:
                if isinstance(response_part, tuple):
                    try:
                        msg = email.message_from_string(response_part[1].decode('utf-8'))
                    except UnicodeDecodeError:
                        msg = email.message_from_string(response_part[1].decode('latin-1'))
                    email_subject = msg['subject']
                    email_from = msg['from']

                    if email_subject is None:
                        email_subject = ""
                    else:
                        email_subject = email.header.make_header(email.header.decode_header(msg['subject']))
                        email_subject = '{}'.format(email_subject)

                    if email_from is None:
                        email_from = ""
                    else:
                        email_from = email.header.make_header(email.header.decode_header(msg['from']))
                        email_from = '{}'.format(email_from)

                    print(str(i) + ':    ' + email_from + ': ' + email_subject + '\n')


    def cd(self, path):
        # //TODO: check if path exists
        if(self.path == path):
            return

        # check if move up requested
        if(path == ".."):
            if Path.get_depth(self.path) == 1:
                self.path = ""
                self.deconnect()
                return

            path = self.path.rsplit('/', 1)
            self.path = path[0]
            return

        # check if email account is selected
        if Path.get_depth(self.path) == 0:
            for account in self.accounts:
                if account.username == path:
                    # set connection
                    self.connect(account.hostname, account.username, account.password)
                    self.path += '/' + path
                    return
            print("Account not found")
            return

        else:
            # move to path
            rc, data = self.connection.select(path)
            if rc == "NO":
                print("path does not exist!")
                return

            self.path += '/' + path
            print(self.path + ' [New: {}]'.format(int(data[0])))

    def view(self, msg_id):
        print(msg_id)
        #rc, data = self.connection.fetch(msg_id, '(RFC822)')
        rc, data = self.connection.uid('fetch', msg_id, '(RFC822)')

        if rc != 'OK':
            print("Could not find message")
            return

        for response_part in data:
            if isinstance(response_part, tuple):
                try:
                    msg = email.message_from_string(response_part[1].decode('utf-8'))
                except UnicodeDecodeError:
                    msg = email.message_from_string(response_part[1].decode('latin-1'))

                email_subject = msg['subject']
                email_from = msg['from']

                if email_subject is None:
                    email_subject = ""

                if email_from is None:
                    email_from = ""

                print("\n")
                for header in ["subject", "from", "to", "date"]:
                    text = email.header.make_header(email.header.decode_header(msg[header]))

                    #print('{:^8}: {}'.format(header.upper(), text))
                print('\n')
                self.parse_part(msg)

    def rm(self, uid):
        self.connection.uid('STORE', uid, '+FLAGS', '(\\Deleted)')

    def ex(self):
        self.connection.expunge()

    def mv(self, uid, dest_path):
        # try RFC 6851 MOVE command
        result = self.connection.uid('MOVE', uid, dest_path)
        if result == 'OK':
            return True

        # else fallback to COPY & DELETE
        result = self.connection.uid('COPY', uid, dest_path)
        if result != 'OK':
            return False

        result, data = imap.uid('STORE', uid, '+FLAGS', '(\Deleted)')
        if result != 'OK':
            return False
        return True



    def parse_part(self, msg):
        if msg.is_multipart():
            for part in msg.get_payload():
                ctype = part.get_content_type()

                if part.is_multipart():
                    self.parse_part(part)

                print('\n' + ctype + '\n')
                if ctype == 'text/plain':
                    try:
                        print(part.get_payload(decode=True).decode('utf-8'))
                    except:
                        dec_msg = msg.get_payload(decode=True)
                        if dec_msg is None:
                            #print(msg)
                            return
                        #print(dec_msg)
                if ctype == 'text/html':
                    try:
                        soup = BeautifulSoup(part.get_payload(decode=True).decode('utf-8'), 'html.parser')
                        for script in soup(["script", "style"]):
                            script.extract()
                        # get text
                        text = soup.get_text()

                        # break into lines and remove leading and trailing space on each
                        lines = (line.strip() for line in text.splitlines())
                        # break multi-headlines into a line each
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        # drop blank lines
                        text = '\n'.join(chunk for chunk in chunks if chunk)

                        print(text)
                    except:
                        soup = BeautifulSoup(part.get_payload(decode=True), 'html.parser')
                        print(soup.get_text())
                        if soup is None:
                            #print(msg)
                            return
                        #print(dec_msg)
        else:
            try:
                print(part.get_payload(decode=True).decode('utf-8'))
            except:
                dec_msg = msg.get_payload(decode=True)
                if dec_msg is None:
                    #print(msg)
                    return
                #print(dec_msg)


    def _parse_list_response(self, line):
        list_response_pattern = re.compile(
            r'\((?P<flags>.*?)\) "(?P<delimiter>.*)" (?P<name>.*)'
        )

        match = list_response_pattern.match(line.decode('utf-8'))
        flags, delimiter, mailbox_name = match.groups()
        mailbox_name = mailbox_name.strip('"')
        return (flags, delimiter, mailbox_name)

    def read_config(self):
        config = configparser.RawConfigParser()
        config.read('conf.ini')

        for section in config.sections():
            if section == "Settings":
                # TODO: do sth useful with settings
                self.settings = config[section]
            else:
                account = MailAccount()
                account.hostname = config[section]['Hostname']
                account.username = section
                account.password = config[section]['Password']

                # copy other account settings
                for (acc_key, acc_val) in config.items(section):
                    if acc_key != "Hostname" and acc_key != "Username" and acc_key != "Password":
                        account.settings[acc_key] = acc_val

                self.accounts.append(account)

                # TODO: refactor to use self.accounts and delete
                self.hostname = config[section]['Hostname']
                self.username = section
                self.password = config[section]['Password']


    def get_bottom_toolbar_tokens(self, cli):
        return [(Token.Toolbar, self.tor_status)]
        #return [(Token.Toolbar, "test")]


    def main(self):
        do_run = True


        toolbar_style = style_from_dict({
            Token.Toolbar: '#0000ff bg:#ffffff',
        })
        history = InMemoryHistory()
        cmd_completer = WordCompleter(['cd', 'ls', 'rm', 'vw', 'mv', 'ex', 'INBOX'])
        while do_run:

            input_command = prompt( '>',
                                    history=history,
                                    auto_suggest=AutoSuggestFromHistory(),
                                    completer=cmd_completer,
                                    get_bottom_toolbar_tokens=self.get_bottom_toolbar_tokens,
                                    style=toolbar_style,
                                    refresh_interval=0.2
                                    )

            # //TODO: add email accounts and boxes to completer
            args = input_command.split(' ')
            command = args[0]

            if command == "ls":
                try:
                    self.ls()
                except KeyboardInterrupt:
                    print("CTRL-C pressed")
                    self.reconnect()

                continue
            if command == "cd":
                # //TODO: check if args.length == 2
                self.cd(args[1])

            if command == "vw":
                # //TODO: check if args.length == 2
                self.view(args[1])

            if command == "rm":
                # //TODO: check if args.length == 2
                self.rm(args[1])

            if command == "ex":
                self.ex()

            if command == "mv":
                # //TODO: check if args.length == 3
                self.ex(args[1], args[2])


class MailAccount:
    def __init__(self):
        self.hostname = ""
        self.username = ""
        self.password = ""
        self.settings = {}


class Path(object):
    def __init__(self):
        return

    @staticmethod
    def is_email_set(path):
        return

    @staticmethod
    def get_depth(path):
        if path == "":  # no email set
            return 0
        return len(path.split('/')) - 1


client = MailClient()
client.read_config()
#client.connect(client.hostname, client.username, client.password)
client.main()
