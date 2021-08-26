import logging
import os
import uuid
from tempfile import NamedTemporaryFile
from typing import Callable, Collection, Dict, Set, Union

from escpos.printer import Dummy, Usb
from telegram import Update
from telegram.ext import CallbackContext, MessageHandler, Updater
from telegram.ext.filters import Filters

logger: logging.Logger = logging.getLogger(__name__)


JsonTypes = Union[str, int, bool]


class POSBot:
    classes: Dict[str, Callable] = {
        "Usb": Usb,
    }

    def __init__(
        self,
        token: str = "",
        printer_class: str = "",
        printer_args: Dict[str, JsonTypes] = {},
        allowed: Collection[int] = [],
    ) -> None:
        self.token = token
        self.printer = self.classes.get(printer_class, Dummy)(**printer_args)
        self.allowed: Set[int] = set(allowed)
        logger.info("POSBot initialized")

    def _acl(f: Callable) -> Callable:  # type: ignore
        def wrapper(self, update: Update, context: CallbackContext) -> None:
            chat_id = update.message.chat_id
            if chat_id not in self.allowed:
                logger.warn("Message from %d was dropped", chat_id)
                return
            f(self, update, context)

        return f

    @_acl
    def _text(self, update: Update, context: CallbackContext) -> None:
        message = update.message.text
        logger.info("Received from %d: %s", update.message.chat_id, message)
        self.printer.textln(message)
        self.printer.cut()

    @_acl
    def _image(self, update: Update, context: CallbackContext) -> None:
        photo = update.message.photo[-1]
        imagefile = context.bot.getFile(photo.file_id)
        logger.info("Received image from %d: %s", update.message.chat_id, imagefile)
        ext = os.path.splitext(imagefile["file_path"])[1]
        with NamedTemporaryFile(suffix=ext) as f:
            logger.info("Writing to %s", f.name)
            imagefile.download(f.name)
            self.printer.image(f.name)
            self.printer.cut()

    def start(self) -> None:
        updater = Updater(self.token)
        dispatcher = updater.dispatcher
        dispatcher.add_handler(MessageHandler(Filters.text, self._text))
        dispatcher.add_handler(MessageHandler(Filters.photo, self._image))
        updater.start_polling()
        updater.idle()
