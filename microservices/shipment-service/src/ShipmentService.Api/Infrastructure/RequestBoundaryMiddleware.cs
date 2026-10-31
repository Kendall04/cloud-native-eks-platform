namespace ShipmentService.Api.Infrastructure;

// Preserve the loopback adapter's JSON body bound when it is eventually removed.
public sealed class RequestBoundaryMiddleware(RequestDelegate next)
{
    public const int MaximumBodyBytes = 16 * 1024;

    public async Task InvokeAsync(HttpContext context)
    {
        context.Response.OnStarting(() =>
        {
            context.Response.Headers.CacheControl = "no-store";
            return Task.CompletedTask;
        });
        if (!(HttpMethods.IsPost(context.Request.Method) || HttpMethods.IsPut(context.Request.Method) || HttpMethods.IsPatch(context.Request.Method)))
        {
            await next(context);
            return;
        }
        if (context.Request.ContentLength > MaximumBodyBytes)
        {
            await Reject(context, StatusCodes.Status413PayloadTooLarge);
            return;
        }
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(context.RequestAborted);
        deadline.CancelAfter(TimeSpan.FromSeconds(8));
        var original = context.Request.Body;
        var bytes = new byte[MaximumBodyBytes + 1];
        var count = 0;
        try
        {
            while (count < bytes.Length)
            {
                var read = await original.ReadAsync(bytes.AsMemory(count), deadline.Token);
                if (read == 0) break;
                count += read;
            }
        }
        catch (OperationCanceledException) when (!context.RequestAborted.IsCancellationRequested)
        {
            await Reject(context, StatusCodes.Status408RequestTimeout);
            return;
        }
        if (count > MaximumBodyBytes)
        {
            await Reject(context, StatusCodes.Status413PayloadTooLarge);
            return;
        }
        await using var body = new MemoryStream(bytes, 0, count, writable: false);
        context.Request.Body = body;
        try { await next(context); }
        finally { context.Request.Body = original; }
    }

    private static Task Reject(HttpContext context, int status)
    {
        context.Response.StatusCode = status;
        return context.Response.WriteAsJsonAsync(new { status, title = "Request body limit exceeded." }, context.RequestAborted);
    }
}
