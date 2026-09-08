<?php
/**
 * Dispatch to the handler named in the request.
 */

require_session();

require __DIR__ . '/handlers/' . $action . '.php';
