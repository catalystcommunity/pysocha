"""Stop indexing when the Pagefind process or response reader fails."""

import asyncio
import signal

from pagefind.service import PagefindService


class CheckedPagefindService(PagefindService):
    """Observe both background tasks while a request waits for its response."""

    async def launch(self):
        await super().launch()
        self._exit_task = asyncio.create_task(self._backend.wait())
        return self

    def _exit_error(self):
        code = self._backend.returncode
        if code is not None and code < 0:
            try:
                reason = signal.Signals(-code).name
            except ValueError:
                reason = "signal {}".format(-code)
            if reason == "SIGILL":
                reason += " (illegal instruction; check binary CPU compatibility)"
        else:
            reason = "exit code {}".format(code)
        return RuntimeError("Pagefind process stopped with {}".format(reason))

    async def send(self, payload):
        request = asyncio.create_task(super().send(payload))
        exited = self._exit_task
        try:
            done, _ = await asyncio.wait(
                (request, exited, self._poll_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if exited in done or self._backend.returncode is not None:
                raise self._exit_error()
            if self._poll_task in done:
                # EOF can reach the reader just before asyncio reaps the child.
                try:
                    await asyncio.wait_for(asyncio.shield(exited), timeout=0.1)
                except asyncio.TimeoutError:
                    pass
                if self._backend.returncode is not None:
                    raise self._exit_error()
                raise RuntimeError("Pagefind response reader failed") from self._poll_task.exception()
            return await request
        finally:
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)

    async def close(self):
        # The upstream close waits for unresolved responses and can raise before
        # it stops the child. Always clean up, including after cancellation.
        for response in self._responses.values():
            response.cancel()
        self._poll_task.cancel()
        await asyncio.gather(self._poll_task, return_exceptions=True)
        if self._backend.returncode is None:
            try:
                self._backend.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(asyncio.shield(self._exit_task), timeout=1)
        except asyncio.TimeoutError:
            try:
                self._backend.kill()
            except ProcessLookupError:
                pass
            await asyncio.wait_for(asyncio.shield(self._exit_task), timeout=1)
