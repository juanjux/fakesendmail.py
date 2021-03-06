#!/usr/bin/env python
"""
Simple fake sendmail program. It will check that the email comes
from an authorized sender and check for spam before calling the
real sendmail. This can be useful to prevent your email delivery service
to be suspended because somebody hacked into your server and started
sending massive amounts of email.

Usually you would rename the sendmail binary and put a link to this program
as /usr/sbin/sendmail. Check that the directory where the program is located is
accesible by any user of sendmail (for example, not a $HOME directory; /opt or
/usr/local are common choices).

Also, make sure that the log directory (by default
/var/log/fakesendmail, configurable with an argument to the constructor) have
write permissions (and exec permissions for the directories) for whatever software
is going to run the fake sendmail.

You would also want to rename or uninstall mailx or any other means to
send email from your server (those spam sending scripts will try everything).
Dont forget to give the script exec permissions (chmod +x)

Author: Juanjo Alvarez <juanjux@gmail.com>

License: MIT https://opensource.org/licenses/mit-license.php
"""

import sys, os, antispam, time, random, string, copy, re, syslog
from email import message_from_string
from subprocess import Popen, PIPE
from traceback import format_exc

pjoin = os.path.join

def get_random_fname():
    return str(int(time.time())) + '_' + \
            ''.join(random.SystemRandom().choice(
                string.ascii_uppercase + string.digits) for _ in range(4)
            )

def real_send(real_sendmail, email_text, params = None):
    params = [] if params is None else params
    cmdlist = [real_sendmail] + params
    ps = Popen(cmdlist, stdin=PIPE, stderr=PIPE)
    ps.stdin.write(email_text)
    (stdout, stderr) = ps.communicate()
    return ps.returncode, stdout,stderr

def joincreate(*args):
    path = pjoin(*args)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

class SpamMessageException(Exception): pass
class UnauthorizedSenderException(Exception): pass

class EmailFilter(object):

    def __init__(self, real_sendmail = '/usr/sbin/ssmtp',
                 log_directory = '/var/log/fakesendmail',
                 notify_info = None):
        """
        Args:
            real_sendmail: the path to the real sendmail-alike binary that will be used
            to deliver message that has passed the tests

            log_directory: the directory where the subfolders with valid/invalid emails
            will be stored and the script log

            notify_info: a dictionary with the keys 'from', 'to' and 'template' with the
            delivery information for problem notifications. The template must be a string
            with {origmsgpath}, {fromaddr} and {toaddr} keys for Python' string.format
            method. With the default value of None no notifications will be sent
            (but the log will still reflect the problems).
        """

        syslog.openlog(ident = 'fakesendmail', facility = syslog.LOG_MAIL)
        self.real_sendmail = real_sendmail

        self.logdir = log_directory
        if not os.path.exists(log_directory):
            os.makedirs(log_directory)

        self.saved_email_path = None
        self.notify_info = notify_info
        self.get_params()

    def log_entry(self, fullpath = None, exctext = None, priority = syslog.LOG_NOTICE):
        msgstr = 'Stored [ {} ]'.format(fullpath)

        if exctext:
            msgstr += 'Exception: [ {} ]'.format(exctext)

        syslog.syslog(msgstr)

    def save_email(self, subdir, suffix = '', priority = syslog.LOG_NOTICE):
        fname = get_random_fname() + suffix
        fullpath = pjoin(joincreate(self.logdir, subdir), fname)
        self.log_entry(fullpath = fullpath, priority = priority)

        with open(fullpath, 'w') as out:
            out.write(self.email_object.as_string())

        self.saved_email_path = fullpath

    def test_validsender(self, valid_senders):
        if valid_senders is None:
            return

        assert self.email_object
        allsenders = copy.copy(self.param_addresses)

        from_email = self.email_object['from'].split()[-1].lower().strip()
        from_email = re.sub(r'[<>]', '', from_email)
        allsenders.append(from_email)

        for sender in allsenders:
            if sender not in valid_senders:
                # Log it and return
                self.save_email('unauthorized_sender', priority = syslog.LOG_WARNING)
                print('ERROR: unathorized sender {0}'.format(sender))
                os._exit(1)

    def test_spam(self, threshold):
        assert self.email_object

        detector = antispam.Detector(
            path = pjoin(joincreate(self.logdir, 'bayesian_model'), 'model.pkl')
        )

        if detector.score(self.email_object.as_string()) > threshold:
            self.save_email('spam', suffix= '_' + str(threshold),
                            priority = syslog.LOG_WARNING)
            print('ERROR: spam email detected')
            os._exit(1)

    def get_params(self):
        self.params = []
        self.param_addresses = []

        inline_addrs = False

        for token in sys.argv[1:]:
            token = token.lower().strip()
            if token[0] == '-':
                self.params.append(token)
                if token == '-t':
                    inline_addrs = True
                continue
            elif not inline_addrs:
                self.param_addresses.append(token)

        if not inline_addrs and not self.param_addresses:
            errmsg = "ERROR: Wrong params, no address list and no -t"
            self.log_entry(exctext = errmsg, priority = syslog.LOG_WARNING)
            os._exit(1)


    def notify_problem(self, error, emailpath):
        if self.notify_info:
            ninfo = self.notify_info
            msg = ninfo['template'].format(
                fromaddr = ninfo['from'],
                toaddr = ninfo['to'],
                error = error,
                origmsgpath = emailpath
            )
            real_send(self.real_sendmail, msg)

    def read_from_stdin(self):
        self.email_object = message_from_string(sys.stdin.read())

    def process_email(self, spam_threshold = 0.45, valid_senders = None):
        """
        Process the email and test for valid sender and spaminess, return
        the code that should be returned to the caller

        Args:
            spam_threshold: the value that the antispam module will use to classify
            an email as spam or not. You can also train it, check:
            http://antispam.readthedocs.io/en/latest/api.html

            valid_senders: a list of valid senders. If used the email has a "From" address
            that is not in this list, the email will not be delivered. Use the None default
            to consider all senders as valid.

        Returns:
            The return value of the real sendmail program or 1 if there was any
            other error.
        """

        try:
            assert self.email_object
            # Find if any of the valid senders is not in the valid senders
            self.test_validsender(valid_senders)

            # Find if its spam
            self.test_spam(spam_threshold)
        except:
            exctext = format_exc()
            print exctext
            self.log_entry(exctext = exctext, priority = syslog.LOG_ERR)
            self.notify_problem(exctext, self.saved_email_path)
            return 1

        # Finally deliver it calling ssmtp with the same parameters we got
        retcode, stdout,stderr = real_send(self.real_sendmail, self.email_object.as_string(),
                                           self.params + self.param_addresses)

        if retcode != 0:
            self.log_entry(exctext = stderr, priority = syslog.LOG_ERR)
            self.save_email('deliver_fail', suffix = '_' + str(retcode),
                            priority = syslog.LOG_ERR)
        else:
            # Delivered, save a copy
            self.save_email('ok')
        return retcode


NOTIFY_TEMPLATE = """
From: {fromaddr}
To: {toaddr}
Subject: Email delivery problem detected

Problem detected with a delivery on the server. The error was:
{error}.

The original message can be find at the path:
{origmsgpath}
"""

# Yeah, change this
VALID_SENDERS = [i.lower().strip() for i in [
    'RotarySpainClub@club-rx8.com',
    'rotaryspainclub@rotaryspainclub.com',
    'admin@rotaryspainclub.com',
    'juanjux@gmail.com',
    'juanjux@yahoo.es',
    'juanjux+web@gmail.com',
    'juanjux+test@gmail.com',
    'juanjo@juanjoalvarez.net',
    ]
]

if __name__  == '__main__':
    notify_info = {
        'from': 'juanjux+web@gmail.com',
        'to': 'juanjux+emailproblems@gmail.com',
        'template': NOTIFY_TEMPLATE,
    }
    f = EmailFilter()
    f.read_from_stdin()
    retcode = f.process_email(valid_senders = VALID_SENDERS)
    os._exit(retcode)
