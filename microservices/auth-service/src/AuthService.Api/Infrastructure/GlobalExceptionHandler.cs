using AuthService.Application.Common.Exceptions;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;

namespace AuthService.Api.Infrastructure;

public sealed class GlobalExceptionHandler(ILogger<GlobalExceptionHandler> logger) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext httpContext,
        Exception exception,
        CancellationToken cancellationToken)
    {
        ProblemDetails problemDetails;

        if (exception is ValidationException validationException)
        {
            problemDetails = new ProblemDetails
            {
                Title = validationException.Title,
                Detail = validationException.Message,
                Status = validationException.StatusCode
            };

            problemDetails.Extensions["errors"] = validationException.Errors;
        }
        else if (exception is AppException appException)
        {
            problemDetails = new ProblemDetails
            {
                Title = appException.Title,
                Detail = appException.Message,
                Status = appException.StatusCode
            };
        }
        else
        {
            logger.LogError(exception, "Unhandled exception while processing request {Method} {Path}", httpContext.Request.Method, httpContext.Request.Path);

            problemDetails = new ProblemDetails
            {
                Title = "Internal Server Error",
                Detail = "An unexpected error occurred while processing the request.",
                Status = StatusCodes.Status500InternalServerError
            };
        }

        httpContext.Response.StatusCode = problemDetails.Status ?? StatusCodes.Status500InternalServerError;
        await httpContext.Response.WriteAsJsonAsync(problemDetails, cancellationToken);
        return true;
    }
}
