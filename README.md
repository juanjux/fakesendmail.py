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
