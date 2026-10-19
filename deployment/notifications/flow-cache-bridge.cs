using System;
using Microsoft.Identity.Client;

// MSAL v4 only permits serialization through notification arguments. Use CLR
// callbacks rather than PowerShell callbacks on the MSAL background thread.
public sealed class DailyNewsFlowCacheBridge
{
    private byte[] data;
    private bool restore;

    public DailyNewsFlowCacheBridge(ITokenCache cache, byte[] initial)
    {
        data = initial == null ? null : (byte[])initial.Clone();
        restore = initial != null;
        cache.SetBeforeAccess(BeforeAccess);
        cache.SetAfterAccess(AfterAccess);
    }

    private void BeforeAccess(TokenCacheNotificationArgs args)
    {
        if (!restore) return;
        args.TokenCache.DeserializeMsalV3(data, true);
        restore = false;
    }

    private void AfterAccess(TokenCacheNotificationArgs args)
    {
        if (data != null) Array.Clear(data, 0, data.Length);
        data = args.TokenCache.SerializeMsalV3();
    }

    public byte[] Export()
    {
        if (data == null) throw new InvalidOperationException("MSAL cache has not been accessed.");
        return (byte[])data.Clone();
    }
}
