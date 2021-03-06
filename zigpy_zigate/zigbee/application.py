import asyncio
import logging

from zigpy.exceptions import DeliveryError
import zigpy.application
import zigpy.util


LOGGER = logging.getLogger(__name__)


class ControllerApplication(zigpy.application.ControllerApplication):
    def __init__(self, zigate, database_file=None):
        super().__init__(database_file=database_file)
        self._zigate = zigate
        self._pending = {}
        self._zigate_seq = {}

    async def startup(self, auto_form=False):
        """Perform a complete application startup"""
        self._zigate.autoStart()
        self._nwk = self._zigate.addr
        self._ieee = self._zigate.ieee

#         self._zigate.add_callback(self.ezsp_callback_handler)

    async def form_network(self, channel=15, pan_id=None, extended_pan_id=None):
        self._zigate.set_channel(channel)
#         if pan_id:
#             self._zigate.set_panid(pan_id)
        if extended_pan_id:
            self._zigate.set_expended_panid(extended_pan_id)

    async def force_remove(self, dev):
        self._zigate.remove_device_ieee(dev.ieee)

#     def ezsp_callback_handler(self, frame_name, args):
#         if frame_name == 'incomingMessageHandler':
#             self._handle_frame(*args)
#         elif frame_name == 'messageSentHandler':
#             if args[4] != t.EmberStatus.SUCCESS:
#                 self._handle_frame_failure(*args)
#             else:
#                 self._handle_frame_sent(*args)
#         elif frame_name == 'trustCenterJoinHandler':
#             if args[2] == t.EmberDeviceUpdate.DEVICE_LEFT:
#                 self.handle_leave(args[0], args[1])
#             else:
#                 self.handle_join(args[0], args[1], args[4])

#     def _handle_frame(self, message_type, aps_frame, lqi, rssi, sender, binding_index, address_index, message):
#         try:
#             device = self.get_device(nwk=sender)
#         except KeyError:
#             LOGGER.debug("No such device %s", sender)
#             return
#
#         device.radio_details(lqi, rssi)
#         try:
#             tsn, command_id, is_reply, args = self.deserialize(device, aps_frame.sourceEndpoint, aps_frame.clusterId, message)
#         except ValueError as e:
#             LOGGER.error("Failed to parse message (%s) on cluster %d, because %s", binascii.hexlify(message), aps_frame.clusterId, e)
#             return
#
#         if is_reply:
#             self._handle_reply(device, aps_frame, tsn, command_id, args)
#         else:
#             self.handle_message(device, False, aps_frame.profileId, aps_frame.clusterId, aps_frame.sourceEndpoint, aps_frame.destinationEndpoint, tsn, command_id, args)
#
#     def _handle_reply(self, sender, aps_frame, tsn, command_id, args):
#         try:
#             send_fut, reply_fut = self._pending[tsn]
#             if send_fut.done():
#                 self._pending.pop(tsn)
#             if reply_fut:
#                 reply_fut.set_result(args)
#             return
#         except KeyError:
#             LOGGER.warning("Unexpected response TSN=%s command=%s args=%s", tsn, command_id, args)
#         except asyncio.futures.InvalidStateError as exc:
#             LOGGER.debug("Invalid state on future - probably duplicate response: %s", exc)
#             # We've already handled, don't drop through to device handler
#             return
#
#         self.handle_message(sender, True, aps_frame.profileId, aps_frame.clusterId, aps_frame.sourceEndpoint, aps_frame.destinationEndpoint, tsn, command_id, args)
#
#     def _handle_frame_failure(self, message_type, destination, aps_frame, message_tag, status, message):
#         try:
#             send_fut, reply_fut = self._pending.pop(message_tag)
#             send_fut.set_exception(DeliveryError("Message send failure: %s" % (status, )))
#             if reply_fut:
#                 reply_fut.cancel()
#         except KeyError:
#             LOGGER.warning("Unexpected message send failure")
#         except asyncio.futures.InvalidStateError as exc:
#             LOGGER.debug("Invalid state on future - probably duplicate response: %s", exc)
#
#     def _handle_frame_sent(self, message_type, destination, aps_frame, message_tag, status, message):
#         try:
#             send_fut, reply_fut = self._pending[message_tag]
#             # Sometimes messageSendResult and a reply come out of order
#             # If we've already handled the reply, delete pending
#             if reply_fut is None or reply_fut.done():
#                 self._pending.pop(message_tag)
#             send_fut.set_result(True)
#         except KeyError:
#             LOGGER.warning("Unexpected message send notification")
#         except asyncio.futures.InvalidStateError as exc:
#             LOGGER.debug("Invalid state on future - probably duplicate response: %s", exc)

    @zigpy.util.retryable_request
    async def request(self, nwk, profile, cluster, src_ep, dst_ep, sequence, data, expect_reply=True, timeout=10):
        assert sequence not in self._pending
        send_fut = asyncio.Future()
        reply_fut = None
        if expect_reply:
            reply_fut = asyncio.Future()
        self._pending[sequence] = (send_fut, reply_fut)

        v = self._zigate.raw_aps_data_request(nwk, src_ep, dst_ep, profile, cluster, data, security=3)
        self._zigate_seq[sequence] = v.sequence

        if v.status != 0:
            self._pending.pop(sequence)
            self._zigate_seq.pop(sequence)
            if expect_reply:
                reply_fut.cancel()
            raise DeliveryError("Message send failure %s" % (v.status, ))

        if expect_reply:
            # Wait for reply
            try:
                v = await asyncio.wait_for(reply_fut, timeout)
            except:  # noqa: E722
                # If we timeout (or fail for any reason), clear the future
                self._pending.pop(sequence)
                self._zigate_seq.pop(sequence)
                raise
        return v

    def permit(self, time_s=60):
        assert 0 <= time_s <= 254
        return self._zigate.permit_join(time_s)
