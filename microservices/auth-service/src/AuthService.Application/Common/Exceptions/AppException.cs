namespace AuthService.Application.Common.Exceptions;

public abstract class AppException : Exception
{
    protected AppException(string title, string message, int statusCode)
        : base(message)
    {
        Title = title;
        StatusCode = statusCode;
    }

    public string Title { get; }

    public int StatusCode { get; }
}

public sealed class ValidationException : AppException
{
    public ValidationException(string message, IReadOnlyCollection<string>? errors = null)
        : base("Validation failed", message, 400)
    {
        Errors = errors ?? Array.Empty<string>();
    }

    public IReadOnlyCollection<string> Errors { get; }
}

public sealed class ConflictException : AppException
{
    public ConflictException(string message)
        : base("Conflict", message, 409)
    {
    }
}

public sealed class NotFoundException : AppException
{
    public NotFoundException(string message)
        : base("Not Found", message, 404)
    {
    }
}

public sealed class UnauthorizedAppException : AppException
{
    public UnauthorizedAppException(string message)
        : base("Unauthorized", message, 401)
    {
    }
}

public sealed class ForbiddenAppException : AppException
{
    public ForbiddenAppException(string message)
        : base("Forbidden", message, 403)
    {
    }
}
