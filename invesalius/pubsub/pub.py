# --------------------------------------------------------------------------
# Software:     InVesalius - Software de Reconstrucao 3D de Imagens Medicas
# Copyright:    (C) 2001  Centro de Pesquisas Renato Archer
# Homepage:     http://www.softwarepublico.gov.br
# Contact:      invesalius@cti.gov.br
# License:      GNU - GPL 2 (LICENSE.txt/LICENCA.txt)
# --------------------------------------------------------------------------
#    Este programa e software livre; voce pode redistribui-lo e/ou
#    modifica-lo sob os termos da Licenca Publica Geral GNU, conforme
#    publicada pela Free Software Foundation; de acordo com a versao 2
#    da Licenca.
#
#    Este programa eh distribuido na expectativa de ser util, mas SEM
#    QUALQUER GARANTIA; sem mesmo a garantia implicita de
#    COMERCIALIZACAO ou de ADEQUACAO A QUALQUER PROPOSITO EM
#    PARTICULAR. Consulte a Licenca Publica Geral GNU para obter mais
#    detalhes.
# --------------------------------------------------------------------------

from typing import Callable, List, Optional, Tuple

from pubsub import pub as Publisher
from pubsub.core.listener import Listener, UserListener

__all__ = [
    # subscribing
    "subscribe",
    "unsubscribe",
    # publishing
    "sendMessage",
    "sendMessage_no_hook",
    # adding hooks
    "add_sendMessage_hook",
    # unsubscribing by owner
    "unsubscribe_owner",
]

Hook = Callable[[str, dict], None]

sendMessage_hook: Optional[Hook] = None


def add_sendMessage_hook(hook: Hook) -> None:
    """Add a hook for sending messages. The hook is a function that takes the topic
    name as the first parameter and the message dict as the second parameter, and
    returns None.

    :param hook:
    """
    global sendMessage_hook
    sendMessage_hook = hook


def subscribe(listener: UserListener, topicName: str, **curriedArgs) -> Tuple[Listener, bool]:
    """Subscribe to a topic.

    :param listener:
    :param topicName:
    :param curriedArgs:
    """
    subscribedListener, success = Publisher.subscribe(listener, topicName, **curriedArgs)  # type: ignore This is a bug in PyPubSub
    return subscribedListener, success


def unsubscribe(*args, **kwargs) -> None:
    """Unsubscribe from a topic."""
    Publisher.unsubscribe(*args, **kwargs)


def unsubscribe_owner(owner: object) -> List[Listener]:
    """Unsubscribe every bound method belonging to an object."""

    def belongs_to_owner(listener: Listener) -> bool:
        callback = listener.getCallable()
        return getattr(callback, "__self__", None) is owner

    return Publisher.unsubAll(listenerFilter=belongs_to_owner)


def sendMessage(topicName: str, **msgdata) -> None:
    """Send a message in a given topic.

    :param topicName:
    :param msgdata:
    """
    Publisher.sendMessage(topicName, **msgdata)
    if sendMessage_hook is not None:
        sendMessage_hook(topicName, msgdata)


def sendMessage_no_hook(topicName: str, **msgdata) -> None:
    """Send a message in a given topic, but do not call the hook.

    :param topicName:
    :param msgdata:
    """
    Publisher.sendMessage(topicName, **msgdata)


AUTO_TOPIC = Publisher.AUTO_TOPIC
ALL_TOPICS = Publisher.ALL_TOPICS
