#include "common_selectors.h"

using std::nullopt;
using std::optional;

namespace nhttp::handler::selectors {

optional<ConnectionState> ValidateRequest::accept(const RequestParser &request) const {
    if (request.method == Method::UnknownMethod) {
        return StatusPage(Status::MethodNotAllowed, request.can_keep_alive(), "Unrecognized method");
    }

    if (request.error_code != Status::UnknownStatus) {
        /*
         * BadRequest may mean badly formed/unparsed request. Always close in
         * that case since there might be leftovers of the unrecognized request
         * lying around.
         */
        return StatusPage(request.error_code, request.error_code == Status::BadRequest ? false : request.can_keep_alive());
    }

    return nullopt;
}

const ValidateRequest validate_request;

optional<ConnectionState> UnknownRequest::accept(const RequestParser &request) const {
    return StatusPage(Status::NotFound, request.can_keep_alive());
}

const UnknownRequest unknown_request;

}
